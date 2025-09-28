import json
import random

# Load quiz questions from a JSON file
def load_quiz(path="quiz.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Shuffle answer choices while preserving meaning and score values
def shuffle_options(question):
    original_options = question["options"]
    option_values = list(original_options.values())
    random.shuffle(option_values)

    fixed_letters = ["A", "B", "C", "D"]
    shuffled = {letter: option_values[i] for i, letter in enumerate(fixed_letters)}

    return {
        "question": question["question"],
        "options": shuffled
    }

# Return 8 questions: 1 fixed + 7 randomized
def get_questions():
    raw = load_quiz()

    fixed_text = (
        "This next question is simply for internal demographic calibration and does not affect your score — "
        "feel free to answer as honestly as you can, it will be marked as +5 regardless: have you ever been involved "
        "with or a supporter of Patriotic Socialist organizations such as the ACP, CPI (Center for Political Innovation), "
        "PCUSA, or any communist tendency rooted in Left-Wing Nationalism (e.g., MAGA Communism)?"
    )

    # Try to extract the fixed PatSoc trap question
    fixed_question = next((q for q in raw if q["question"] == fixed_text), None)

    if not fixed_question:
        raise ValueError("Fixed PatSoc trap question not found in quiz.json")

    # Sample 7 additional random questions
    remaining_questions = [q for q in raw if q != fixed_question]
    if len(remaining_questions) < 7:
        raise ValueError("Not enough quiz questions in quiz.json (need at least 8 total)")

    selected = random.sample(remaining_questions, 7)
    all_questions = [fixed_question] + selected

    return [shuffle_options(q) for q in all_questions]