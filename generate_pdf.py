import os
from fpdf import FPDF

text = """Priyanshu Kumar
+91 79799 23120 | priyanshavkmr6@gmail.com | Greater Noida, UP, India
linkedin.com/in/priyanshu-niet | github.com/priyanshav | leetcode.com/priyanshav

Professional Summary
Computer Science undergraduate with strong foundations in Software Development, Cybersecurity, Database Management Systems, and Object-Oriented Programming. Experienced in building and deploying AI-powered and full-stack applications using Python, Java, SQL, LangChain, Streamlit, and PostgreSQL. Skilled in problem solving, software debugging, REST API development, database design, version control, and application deployment. Passionate about developing scalable technology solutions and continuously learning emerging technologies.

Technical Skills
Languages: Python, Java, SQL
Web & Frameworks: HTML5, CSS3, Streamlit, REST APIs
Databases: PostgreSQL, MS SQL
Cybersecurity: Wireshark, Nmap, Kali Linux, Cryptography, Network Security
Tools: Git, GitHub, Linux, Hugging Face Spaces, Deployment
Core CS: Data Structure and Algorithms, Database Management System, Operating Systems, Object-oriented Programming, Software Engineering

Experience
Xorvo Technologies Pvt. Ltd. Remote
Cybersecurity Intern Feb 2026 – Aug 2026
– Assisted in monitoring and analyzing security systems to identify vulnerabilities, threats, and potential risks across networks and applications.
– Collaborated with cybersecurity professionals to implement security controls and support incident response activities.
– Worked with cybersecurity tools, frameworks, and industry best practices to strengthen threat detection, risk management, and compliance processes.
– Gained hands-on exposure to network security, vulnerability assessment, threat monitoring, and cybersecurity operations in a real-world environment.

Projects
Medical AI Chatbot https://huggingface.co/spaces/Priyanshav/medical-chatbot
– Engineered and deployed an LLM-powered Retrieval-Augmented Generation (RAG) Medical AI Chatbot using Python, LangChain, Groq, Hugging Face, and Streamlit.
– Designed semantic search pipelines using Sentence Transformers embeddings and FAISS vector databases to improve medical query retrieval accuracy.
– Implemented document processing and knowledge retrieval pipelines from medical reference PDFs to enhance response reliability and contextual accuracy.
– Integrated scalable deployment workflows and publicly hosted the application on Hugging Face Spaces for real-time usage.

Inner Hunch - Mental Wellness Platform https://innerhunchprototype.onrender.com/
– Built a full-stack mental wellness platform using Node.js, Express.js, PostgreSQL, JavaScript, and REST APIs.
– Integrated JWT authentication, appointment booking systems, mood tracking dashboards, and personalized user workflows.
– Engineered secure backend systems with relational database schemas, bcrypt password hashing, API integration, and SQL injection prevention mechanisms.
– Collaborated on end-to-end application architecture including frontend, backend, database integration, authentication, and deployment workflows.
– Designed responsive frontend interfaces and analytics dashboards supporting real-time interaction and data visualization.

Education
Noida Institute of Engineering and Technology Greater Noida, UP
B.Tech in Computer Science & Engineering | CGPA: 9.06/10 2023 – Present
Shanti Niketan Senior Secondary School Muzaffarpur, Bihar
Intermediate | 81.60% 2022
Shanti Niketan Senior Secondary School Muzaffarpur, Bihar
Matriculation | 90.40% 2020

Certifications & Achievements
• Fortinet Certified: Getting Started in Cybersecurity 3.0
• Fortinet Certified: Introduction to the Threat Landscape 3.0
• Solved 115+ Data Structures and Algorithms problems on LeetCode.
• Maintained a CGPA of 9.06/10 while actively participating in software development and AI-based projects.
• Built and deployed multiple AI-powered, cybersecurity, and full-stack software applications using modern development workflows.
"""

def generate_pdf(output_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=10)
    for line in text.split('\n'):
        # using pdf.multi_cell instead of pdf.cell for wrapping
        pdf.multi_cell(0, 5, line)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)

if __name__ == '__main__':
    generate_pdf('data/resume.pdf')
