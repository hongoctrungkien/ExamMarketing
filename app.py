from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pandas as pd
import random, os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
#import datetime

app = Flask(__name__)
app.secret_key = "secret_key_change_me"

# ====== CHATBOT ======
# ==== Load dữ liệu Excel ====
data = pd.read_excel("QA.xlsx")   # cột Question và Answer
questions = data["Question"].astype(str).tolist()
answers = data["Answer"].astype(str).tolist()

# ==== Train TF-IDF ====
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(questions)

def chatbot_response(user_input: str) -> str:
    """Trả lời dựa trên câu hỏi gần nhất trong Excel"""
    user_vec = vectorizer.transform([user_input])
    similarity = cosine_similarity(user_vec, X).flatten()
    idx = similarity.argmax()
    if similarity[idx] < 0.3:  # Ngưỡng tin cậy
        return "Xin lỗi, tôi chưa hiểu câu hỏi của bạn."
    return answers[idx]

@app.route("/")
def home():
    return render_template("exam_index.html")

@app.route("/chat", methods=["POST"])
def ask():
    user_input = request.json.get("message", "")
    reply_raw = chatbot_response(user_input)
    # format: chào đầu và thân mến ở cuối
    reply = f"Chào bạn, \n{reply_raw}\nThân mến."
    return jsonify({"reply": reply})

# ====== QUIZ TỪNG CHƯƠNG ======
QUESTIONS_XLSX = "CH.xlsx"

def load_questions_for_chapter(chapter_id):
    df = pd.read_excel(QUESTIONS_XLSX)
    chapter_df = df[df["ID"] == int(chapter_id)].dropna(subset=["CauHoi","A","B","C","D","DapAn"])
    questions = []
    for _, row in chapter_df.iterrows():
        opts = [str(row["A"]), str(row["B"]), str(row["C"]), str(row["D"])]
        corr = str(row["DapAn"]).strip()
        corr_idx = int(corr)-1 if corr.isdigit() else {"A":0,"B":1,"C":2,"D":3}.get(corr.upper(),0)
        shuffled = opts[:]; random.shuffle(shuffled)
        correct_text = opts[corr_idx]
        new_correct = shuffled.index(correct_text)
        questions.append({"question": str(row["CauHoi"]),"options": shuffled,"correct_index": new_correct})
    random.shuffle(questions)
    return questions

@app.route("/quiz")
def quiz_index():
    if not os.path.exists(QUESTIONS_XLSX):
        return "CH.xlsx không tồn tại."
    df = pd.read_excel(QUESTIONS_XLSX)
    chapters = sorted(df["ID"].dropna().unique().tolist())
    return render_template("quiz_index.html", chapters=chapters)

@app.route("/quiz/start", methods=["POST"])
def quiz_start():
    data = request.json or {}
    chapter = data.get("chapter")
    if not chapter:
        return jsonify({"error":"chapter required"}),400
    questions = load_questions_for_chapter(chapter)
    if not questions:
        return jsonify({"error":"Không tìm thấy câu hỏi"}),404
    session["quiz"] = {"chapter": chapter,"questions": questions,"current": 0,
                       "answers": [None]*len(questions),"answered": [False]*len(questions)}
    return jsonify({"ok":True,"num_questions":len(questions)})

@app.route("/quiz/play")
def quiz_play():
    if "quiz" not in session: return redirect(url_for("quiz_index"))
    return render_template("quiz_player.html")

@app.route("/quiz/question")
def quiz_question():
    quiz = session.get("quiz")
    if not quiz: return jsonify({"error":"no_quiz"}),400
    idx = quiz["current"]
    q = quiz["questions"][idx]
    payload = {"index": idx,"num_questions": len(quiz["questions"]),
               "question": q["question"],"options": q["options"],
               "answered": quiz["answered"][idx],"selected": quiz["answers"][idx]
               }
    
    if quiz["answered"][idx]: payload["correct_index"] = q["correct_index"]
    return jsonify(payload)

@app.route("/quiz/answer", methods=["POST"])
def quiz_answer():
    body = request.json or {}
    sel = body.get("selected")
    quiz = session.get("quiz")
    if not quiz: return jsonify({"error":"no_quiz"}),400
    idx = quiz["current"]
    if quiz["answered"][idx]: return jsonify({"ok":False,"message":"Đã trả lời"}),200
    quiz["answers"][idx] = int(sel)
    quiz["answered"][idx] = True
    session["quiz"]=quiz
    correct = int(sel) == quiz["questions"][idx]["correct_index"]
    return jsonify({"ok":True,"correct": correct,"correct_index":quiz["questions"][idx]["correct_index"]})

@app.route("/quiz/goto", methods=["POST"])
def quiz_goto():
    body = request.json or {}
    act = body.get("action")
    quiz = session.get("quiz")
    if not quiz: return jsonify({"error":"no_quiz"}),400
    idx = quiz["current"]
    if act=="next" and idx < len(quiz["questions"])-1: idx+=1
    elif act=="prev" and idx>0: idx-=1
    elif isinstance(act,int) or (isinstance(act,str) and act.isdigit()): idx=int(act)
    quiz["current"]=idx; session["quiz"]=quiz
    return jsonify({"ok":True,"current":idx})

@app.route("/quiz/result")
def quiz_result():
    quiz = session.get("quiz")
    if not quiz: return jsonify({"error":"no_quiz"}),400
    total = len(quiz["questions"])
    answered = sum(1 for a in quiz["answered"] if a)
    correct = sum(1 for i,a in enumerate(quiz["answers"]) if a==quiz["questions"][i]["correct_index"])
    return jsonify({"total":total,"answered":answered,"correct":correct})

# ====== PHẦN THI LỚN KIỂU TESTTHI.PY ======
QUESTIONS_XLSX = "CH.xlsx"

# Biến global lưu câu hỏi để tránh lưu quá nhiều trong session
EXAM_QUESTIONS = []

# ==================== Trang nhập thông tin ====================
@app.route("/exam")
def exam_index_page():
    return render_template("exam_index.html")

@app.route("/exam/start", methods=["POST"])
def exam_start():
    global EXAM_QUESTIONS
    data = request.json or {}
    name = data.get("name", "").strip()
    cls = data.get("class", "").strip()
    password_input = data.get("password", "").strip()

    if not name or not cls or not password_input:
        return jsonify({"ok": False, "error": "Vui lòng nhập đầy đủ Tên, Lớp và Mật khẩu!"})

    now = datetime.now()
    correct_password = f"{now.month:02}{now.hour:02}{now.day:02}"

    if password_input != correct_password:
        return jsonify({"ok": False, "error": "Mật khẩu phòng thi không đúng!"})

    # Chuẩn bị câu hỏi: 6 chương, mỗi chương 10 câu ngẫu nhiên
    df = pd.read_excel(QUESTIONS_XLSX).dropna(subset=["CauHoi","A","B","C","D","DapAn"])
    questions = []
    grouped = df.groupby("ID")
    for chapter_id, group in grouped:
        chapter_questions = group.sample(n=min(10,len(group))).reset_index(drop=True)
        for _, row in chapter_questions.iterrows():
            opts = [str(row["A"]), str(row["B"]), str(row["C"]), str(row["D"])]
            corr = str(row["DapAn"]).strip()
            mapping = {"A":0,"B":1,"C":2,"D":3}
            corr_idx = mapping.get(corr.upper(),0) if not corr.isdigit() else int(corr)-1
            shuffled = opts[:]
            random.shuffle(shuffled)
            correct_text = opts[corr_idx]
            new_correct = shuffled.index(correct_text)
            questions.append({
                "question": row["CauHoi"],
                "options": shuffled,
                "correct_index": new_correct
            })

    random.shuffle(questions)
    EXAM_QUESTIONS = questions

    # Session lưu nhỏ gọn
    session["exam"] = {
        "name": name,
        "class": cls,
        "answers": [None]*len(questions),
        "answered": [False]*len(questions),
        "current": 0
    }

    return jsonify({"ok": True, "redirect": url_for("exam_play")})

# ==================== Giao diện thi ====================
@app.route("/exam/play")
def exam_play():
    if "exam" not in session:
        return redirect(url_for("exam_index_page"))
    return render_template("exam_player.html")

@app.route("/exam/question")
def exam_question():
    exam = session.get("exam")
    if not exam:
        return jsonify({"error":"no_exam"}),400
    idx = exam["current"]
    q = EXAM_QUESTIONS[idx]
    payload = {
        "index": idx,
        "num_questions": len(EXAM_QUESTIONS),
        "question": q["question"],
        "options": q["options"],
        "answered": exam["answered"][idx],
        "selected": exam["answers"][idx],
        "answers": exam["answers"],      # Thêm dòng này
        "answered_all": exam["answered"], # Thêm dòng này
        "submitted": exam.get("submitted", False),
        "questions": EXAM_QUESTIONS 
    }
    if exam.get("submitted", False):
        payload["correct_index"] = q["correct_index"]
    if exam["answered"][idx]:
        payload["correct_index"] = q["correct_index"]
    return jsonify(payload)

@app.route("/exam/answer", methods=["POST"])
def exam_answer():
    data = request.json or {}
    sel = data.get("selected")
    exam = session.get("exam")
    if not exam: return jsonify({"error":"no_exam"}),400
    idx = exam["current"]

    # Bỏ điều kiện không cho chọn lại
    exam["answers"][idx] = int(sel)
    exam["answered"][idx] = True  # vẫn đánh dấu đã trả lời
    session["exam"] = exam
    correct = (int(sel) == EXAM_QUESTIONS[idx]["correct_index"])
    return jsonify({"ok":True,"correct":correct,"correct_index":EXAM_QUESTIONS[idx]["correct_index"]})

@app.route("/exam/goto", methods=["POST"])
def exam_goto():
    data = request.json or {}
    act = data.get("action")
    exam = session.get("exam")
    if not exam:
        return jsonify({"error":"no_exam"}),400
    idx = exam["current"]
    if act=="next" and idx<len(EXAM_QUESTIONS)-1: idx+=1
    elif act=="prev" and idx>0: idx-=1
    elif isinstance(act,int) or (isinstance(act,str) and act.isdigit()): idx=int(act)
    exam["current"]=idx
    session["exam"]=exam
    return jsonify({"ok":True,"current":idx})

@app.route("/exam/submit", methods=["POST"])
def exam_submit():
    exam = session.get("exam")
    if not exam: return jsonify({"error":"no_exam"}),400
    total=len(EXAM_QUESTIONS)
    answered=sum(1 for a in exam["answered"] if a)
    correct=0
    details=[]
    for i,q in enumerate(EXAM_QUESTIONS):
        sel=exam["answers"][i]
        corr=q["correct_index"]
        is_corr=(sel is not None and sel==corr)
        if is_corr: correct+=1
        details.append({"index":i,"question":q["question"],"options":q["options"],
                        "selected":sel,"correct":corr,"is_correct":is_corr})
    # Lưu kết quả
    # Lưu kết quả
    result_folder = "report"
    os.makedirs(result_folder, exist_ok=True)
    result_path = os.path.join(result_folder, "diem.xlsx")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result_data = {
        "Tên": exam["name"],
        "Lớp": exam["class"],
        "Thời gian": now,
        "Điểm": round(correct / total * 100)
    }
    for i, d in enumerate(details):
        result_data[f"Câu {i+1}"] = "Đúng" if d["is_correct"] else "Sai"

    df_new = pd.DataFrame([result_data])

    # Nếu file tồn tại → nối thêm
    if os.path.exists(result_path):
        df_existing = pd.read_excel(result_path)
        df_concat = pd.concat([df_existing, df_new], ignore_index=True)
        df_concat.to_excel(result_path, index=False)
    else:
        df_new.to_excel(result_path, index=False)

    # Xóa session
    exam["submitted"] = True
    session["exam"] = exam
    #session.pop("exam",None)
    return jsonify({"total":total,"answered":answered,"correct":correct,"details":details})

@app.route("/exam/exit", methods=["POST"])
def exam_exit():
    exam = session.get("exam")
    if exam and not exam.get("submitted"):
        # Gửi submit tự động trước khi thoát
        exam_submit_data = exam_submit()
    # Xóa session
    session.pop("exam", None)
    return jsonify({"ok": True, "redirect": "/"})
    
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000)
