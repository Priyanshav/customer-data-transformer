import json
import csv
from reportlab.pdfgen import canvas

# Ananya - Resume with the exact formatting that caused bugs
c = canvas.Canvas("data/ananya.pdf")
c.drawString(100, 800, "Ananya Gupta")
c.drawString(100, 780, "ananya.gupta@example.com")
c.drawString(100, 760, "9234567810")
c.drawString(100, 740, "Skills: SIEM, Wazuh, Splunk, Python, Linux")
c.drawString(100, 700, "Experience")
c.drawString(100, 680, "Education")
c.drawString(100, 660, "2 years of relevant industry experience.")
c.drawString(100, 640, "Cybersecurity Analyst")
c.save()

# Vikram - CSV with explicit phone +19345678120 and +919345678120?
# The bug was two sources with same number but one missing country code.
# Let's give Vikram CSV with +91... and JSON with no country code.
with open("data/vikram.csv", "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["Name", "Email", "Phone", "Skills", "Company", "Title"])
    writer.writeheader()
    writer.writerow({
        "Name": "Vikram Singh",
        "Email": "vikram.singh@example.com",
        "Phone": "+919345678120",
        "Skills": "Python, SQL, Power Bi, Excel, Pandas",
        "Company": "Data Analyst",
        "Title": ""
    })

# JSON for Vikram with no country code
with open("data/vikram.json", "w") as f:
    json.dump([{
        "first_name": "Vikram",
        "last_name": "Singh",
        "email": "vikram.singh@example.com",
        "phone": "9345678120"
    }], f)

# Let's add Rahul to JSON
with open("data/rahul.json", "w") as f:
    json.dump([
        {
            "first_name": "Rahul",
            "last_name": "Verma",
            "email": "rahul.verma@example.com",
            "phone": "9123456780",
            "skills": ["Java", "Spring Boot", "Mysql", "Docker", "AWS"],
            "experience": [{"company": "Java Backend Developer", "title": ""}]
        }
    ], f)

with open("data/rahul.csv", "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["Name", "Email", "Phone"])
    writer.writeheader()
    writer.writerow({
        "Name": "Rahul Verma",
        "Email": "rahul.verma@example.com",
        "Phone": "+919123456780"
    })
