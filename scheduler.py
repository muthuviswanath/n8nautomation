import datetime
from dateutil import parser
import pytz
import math

def parse_time(tstr):
    h, m = map(int, tstr.split(":"))
    return datetime.time(hour=h, minute=m)

def to_dt(date_str, time_str, tz):
    d = datetime.date.fromisoformat(date_str)
    h, m = map(int, time_str.split(":"))
    return tz.localize(datetime.datetime(d.year, d.month, d.day, h, m))

class SchedulerEngine:
    def __init__(self, tz_name="Asia/Kolkata"):
        self.tz = pytz.timezone(tz_name)

    def _events_to_busy_intervals(self, calendar_events, date):
        busy = []
        for e in calendar_events:
            try:
                s = parser.isoparse(e["start"])
                eend = parser.isoparse(e["end"])
            except:
                continue
            if s.date() != date:
                continue
            busy.append((s.astimezone(self.tz), eend.astimezone(self.tz)))
        busy.sort()
        merged = []
        for s, e in busy:
            if not merged:
                merged.append((s, e))
            else:
                last_s, last_e = merged[-1]
                if s <= last_e:
                    merged[-1] = (last_s, max(last_e, e))
                else:
                    merged.append((s, e))
        return merged

    def _free_slots(self, busy_intervals, work_start_dt, work_end_dt, buffer_min):
        slots = []
        cur = work_start_dt
        for s, e in busy_intervals:
            bstart = s - datetime.timedelta(minutes=buffer_min)
            bend = e + datetime.timedelta(minutes=buffer_min)
            if bstart > cur:
                slots.append((cur, bstart))
            cur = max(cur, bend)
        if cur < work_end_dt:
            slots.append((cur, work_end_dt))
        return [ (a, b) for a, b in slots if (b - a).total_seconds() >= 60 ]

    def score_task(self, task, today_date_iso):
        score = 0.0
        importance = float(task.get("importance", 3))
        score += importance * 2.0
        if task.get("deadline"):
            dl = datetime.date.fromisoformat(task["deadline"])
            today = datetime.date.fromisoformat(today_date_iso)
            days_left = (dl - today).days
            if days_left < 0:
                days_cv = 5.0
            elif days_left == 0:
                days_cv = 4.0
            else:
                days_cv = max(0.5, 3.0 / (days_left + 1))
            score += days_cv
        score += float(task.get("goal_match", 0.0)) * 3.0
        est = float(task.get("estimate_min", 30))
        score += 1.0 / (1.0 + math.log1p(est))
        return score

    def optimize_day(self, payload):
        date_iso = payload.get("date", datetime.date.today().isoformat())
        date_obj = datetime.date.fromisoformat(date_iso)
        calendar_events = payload.get("calendar_events", [])
        tasks = payload.get("tasks", [])
        work_hours = payload.get("work_hours", {"start": "09:00", "end": "18:00"})
        buffer_min = int(payload.get("buffer_min", 10))

        busy = self._events_to_busy_intervals(calendar_events, date_obj)
        ws = to_dt(date_iso, work_hours["start"], self.tz)
        we = to_dt(date_iso, work_hours["end"], self.tz)
        free_slots = self._free_slots(busy, ws, we, buffer_min)

        for t in tasks:
            t["score"] = self.score_task(t, date_iso)
        tasks.sort(key=lambda x: (-x["score"], x.get("deadline") or "9999-12-31", int(x.get("estimate_min", 30))))

        scheduled, unscheduled = [], []

        def fit_task(task):
            dur = datetime.timedelta(minutes=int(task.get("estimate_min", 30)))
            for i, (s, e) in enumerate(free_slots):
                if (e - s) >= dur:
                    start, end = s, s + dur
                    scheduled.append({
                        "task_id": task.get("id"),
                        "title": task.get("title"),
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "score": task.get("score")
                    })
                    new_slots = []
                    if start > s:
                        new_slots.append((s, start))
                    if end < e:
                        new_slots.append((end, e))
                    free_slots.pop(i)
                    for ns in reversed(new_slots):
                        free_slots.insert(i, ns)
                    return True
            return False

        for t in tasks:
            if not fit_task(t):
                unscheduled.append(t)

        return {
            "date": date_iso,
            "scheduled": scheduled,
            "unscheduled": [u.get("title") for u in unscheduled],
            "free_slots": [
                {"start": a.isoformat(), "end": b.isoformat(),
                 "minutes": int((b - a).total_seconds() / 60)} for (a, b) in free_slots
            ]
        }
