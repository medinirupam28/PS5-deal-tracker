import schedule
import time


def start_scheduler(task, interval_hours=2):
    print(f"PS5 Deal Tracker running. Checks every {interval_hours} hours.")
    task()
    schedule.every(interval_hours).hours.do(task)
    while True:
        schedule.run_pending()
        time.sleep(20)
