"""Build the Devgarh test dataset (fictional): an X/Twitter-style CSV export + an incident log.

Everything is invented: the district (Devgarh), communities ("Community X"/"Community Y"), people,
handles, phone numbers and URLs (.example). Times are written in UTC ("Z") like a real API export.

    python make_devgarh.py      -> devgarh_posts.csv, devgarh_incidents.csv
"""
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

rng = random.Random(7)
HERE = Path(__file__).parent
IST = timezone(timedelta(hours=5, minutes=30))
DAY = datetime(2026, 10, 5, tzinfo=IST)  # a Monday
rows, n = [], [0]


def utc(h, m, s=0):
    return (DAY.replace(hour=h, minute=m, second=s)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def acct(name, followers, age_days):
    created = (DAY - timedelta(days=age_days)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"screen_name": name, "user_id": f"U{abs(hash(name)) % 10**6:06d}", "followers_count": followers,
            "user_created_at": created}


def post(a, text, h, m, s=0, rt=None, reply=None, src="Twitter for Android"):
    n[0] += 1
    rows.append({"tweet_id": f"17{n[0]:04d}", "screen_name": a["screen_name"], "user_id": a["user_id"],
                 "full_text": text, "created_at": utc(h, m, s), "followers_count": a["followers_count"],
                 "user_created_at": a["user_created_at"], "retweeted_status_id": rt or "",
                 "in_reply_to_status_id": reply or "", "source": src})
    return rows[-1]["tweet_id"]


# --- ordinary posts (should NOT be flagged) ---------------------------------------------------
ordinary = [
    ("devgarh_foodie", "Devgarh ke purane bazaar mein nayi lassi shop khuli hai, must try!"),
    ("traffic_devgarh", "Ring road pe accident ki wajah se jam hai, alternate route lein."),
    ("meera_teacher", "Proud of my class 10 students, 100% pass result this year!"),
    ("cricket_pagal_21", "We are going to destroy them tonight! Come on India, bring the cup home 🏏"),
    ("aam_aadmi_devgarh", "MLA saab ne 5 saal mein ek road nahi banayi. Is baar vote soch samajh ke dena."),
    ("devgarh_news_live", "Devgarh police ne ek aadmi ko giraftar kiya jo online dhamki de raha tha. Case darj."),
    ("weather_devgarh", "आज देवगढ़ में हल्की बारिश, शाम को मौसम सुहाना रहेगा।"),
    ("rohit_runs", "Morning 5k done at Devgarh lake. Who is joining tomorrow?"),
    ("chai_adda_dg", "Chai aur pakode, baarish ka best combo ☕"),
    ("dr_anjali_clinic", "Free diabetes check-up camp at Civil Hospital this Saturday, 9am to 1pm."),
    ("bookworm_priya", "Finished reading a great novel today. Recommendations welcome!"),
    ("devgarh_municipal", "Water supply in Ward 12 will be off tomorrow 10am-2pm for pipeline repair."),
    ("startup_sahil", "Hiring two interns for our Devgarh office, DM me your CV."),
    ("film_critic_dg", "Nayi film ka second half boring tha, songs ache the. 3/5"),
    ("pet_lover_neha", "Found a lost brown dog near Station Road, owner please contact the animal shelter."),
    ("kisan_ramesh", "Is saal barish achhi hui, dhaan ki fasal badhiya hogi."),
    ("student_union_dg", "Peaceful candle march for road safety awareness, Sunday 6pm, Town Hall. All welcome."),
    ("history_buff_dg", "Purana Qila was built in the 16th century, beautiful architecture!"),
    ("mom_of_two_dg", "School bus timings changed from Monday, parents please note."),
    ("gym_bro_dg", "Leg day done, can't walk now 😂"),
    ("local_reporter_ak", "Report: Devgarh nagar nigam ne 3 naye public toilets banaye, lekin paani ki dikkat abhi bhi."),
    ("comedy_dg", "Mera WiFi meri life se zyada slow hai 😂"),
]
for i, (name, text) in enumerate(ordinary):
    post(acct(name, rng.randint(150, 30000), rng.randint(400, 3000)), text, 7 + i % 14, rng.randint(0, 59))

# --- Campaign A: incitement + mobilisation, #DevgarhJago (14 fresh accounts) --------------------
fresh = [acct(f"sher_{rng.randint(1000, 9999)}", rng.randint(3, 45), rng.randint(1, 4)) for _ in range(14)]
claim = [
    "Devgarh mein Community X ke logon ne mandir ke bahar pathar phenke, police so rahi hai! #DevgarhJago",
    "Kal raat Community X walon ne mandir pe pathar phenke aur police chup hai. #DevgarhJago",
]
c1 = post(fresh[0], claim[0], 10, 2)
c2 = post(fresh[1], claim[1], 10, 6)
for i, a in enumerate(fresh[2:7]):
    post(a, claim[i % 2], 10, 11 + i, rng.randint(0, 59), rt=[c1, c2][i % 2])
share = ["Share karo, sabko batao! Community X ne mandir pe pathar phenke, media chup hai. #DevgarhJago",
         "Sabko batao, share karo! Mandir pe pathar phenke gaye, koi action nahi. #DevgarhJago"]
for i, a in enumerate(fresh[4:10]):
    post(a, share[i % 2], 10, 14 + i, rng.randint(0, 59))
hostile = ["Ab chup nahi baithenge, Community X ko sabak sikhana padega! #DevgarhJago",
           "Bahut ho gaya, Community X ko jawab dena padega. Ab chup nahi baithenge. #DevgarhJago"]
for i, a in enumerate(fresh[8:13]):
    post(a, hostile[i % 2], 10, 22 + i, rng.randint(0, 59))
mob = ["Kal Tuesday subah 10 baje Purana Qila gate pahuncho, sab ikattha ho! #DevgarhJago",
       "Sab log kal Tuesday subah 10 baje Purana Qila gate pahuncho, ek saath jawab denge! #DevgarhJago"]
for i, a in enumerate([fresh[0], fresh[1], fresh[9], fresh[11], fresh[12], fresh[13]]):
    post(a, mob[i % 2], 10, 30 + 2 * i, rng.randint(0, 59))

# --- Campaign B: health misinformation, #DevgarhPaniAlert (8 accounts, mixed ages) --------------
mixed = [acct(f"alert_dg_{i}", rng.randint(10, 60), rng.randint(2, 10)) for i in range(5)] + \
        [acct(n_, rng.randint(300, 2000), rng.randint(300, 900)) for n_ in ("worried_papa_dg", "nani_ki_rasoi", "dg_moms_group")]
fake = ["Devgarh ki paani ki tanki mein zeher mila diya gaya hai, 20 log hospital mein! Prashasan chhupa raha hai. #DevgarhPaniAlert",
        "BREAKING: Devgarh tanki ka paani zeher wala hai, prashasan chhupa raha hai, nal ka paani mat piyo! #DevgarhPaniAlert",
        "Forward karo! Devgarh ki tanki mein zeher, bachchon ko nal ka paani mat do. #DevgarhPaniAlert"]
for i, a in enumerate(mixed):
    post(a, fake[i % 3], 16, 5 + 3 * i, rng.randint(0, 59))
for i, a in enumerate(mixed[:4]):
    post(a, fake[(i + 1) % 3], 16, 30 + 2 * i, rng.randint(0, 59))

# --- Standalone violations ------------------------------------------------------------------
post(acct("sbi_care_helpdesk", 22, 3),
     "Dear customer, your SBI account will be blocked today. Share your card number and OTP with us on 9876012345 for KYC update.",
     11, 40)
post(acct("bhola_gussa", 90, 200),
     "@dr_anjali_clinic meri maa ka ilaaj galat kiya tumne, hospital se nikalte hi dekh lena, chhodenge nahi.", 13, 15)
post(acct("expose_karo_dg", 15, 5),
     "Is ladki ka number 9123409876 hai aur yeh roz Station Road coaching jaati hai, sab isse milo aur sabak sikhao.", 14, 5)
post(acct("dukaan_rival", 140, 500),
     "Gupta Kirana wala milawati atta bechta hai aur logon ko bimaar karta hai, koi mat khareedo, chor hai woh!", 15, 20)
post(acct("troll_king_dg", 30, 20),
     "Community Y ke log apne bhagwan ki pooja karte hain, kitne bewakoof hain, unki aastha ka mazaak udao sab.", 19, 45)
post(acct("devgarh_police_official", 12, 2),
     "OFFICIAL: Devgarh Police challan clear karne ke liye is link pe payment karein https://devgarh-challan.example/pay aur apna OTP daalein.",
     20, 10)

rows.sort(key=lambda r: r["created_at"])
with (HERE / "devgarh_posts.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

incidents = [
    {"incident_id": "DG-01", "reported_at": "2026-10-05T08:30:00+05:30", "district": "Devgarh",
     "location": "Devgarh mandir road", "category": "clash",
     "description": "Argument between two vendors near the temple road; one person hurt, situation controlled",
     "source": "Mock control-room log"},
    {"incident_id": "DG-02", "reported_at": "2026-10-05T17:40:00+05:30", "district": "Devgarh",
     "location": "Civil Hospital", "category": "panic",
     "description": "Crowd of worried residents at Civil Hospital after a water-poisoning rumour; no poisoning found",
     "source": "Mock control-room log"},
    {"incident_id": "DG-03", "reported_at": "2026-10-05T09:10:00+05:30", "district": "Devgarh",
     "location": "Ring road", "category": "accident", "description": "Two-wheeler skid, minor injury",
     "source": "Mock control-room log"},
]
with (HERE / "devgarh_incidents.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(incidents[0]))
    w.writeheader()
    w.writerows(incidents)
print(f"{len(rows)} posts, {len(incidents)} incidents written to {HERE}")
