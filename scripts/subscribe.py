import redis
import time
def run():
    r = redis.Redis(host="localhost")
    p = r.pubsub()
    p.subscribe('code')
    while True:
        try:
            otp = p.get_message()
            print(otp)
            if otp:
                print(otp["data"])
                otpa = list(otp)
                print(otpa)
                digits = [s.isdigit() for s in otpa]
                if not(digits) or (not all(digits)) or len(digits)!=4:
                    continue
                break 
        except redis.ConnectionError:
            p = r.pubsub()
            p.subscribe(channel)
        time.sleep(1)  

