import re, json, argparse
from pathlib import Path

ID_RE = re.compile(r"^[A-Z]{1,3}\d+-\d{3}\s*$")
OPT_RE = re.compile(r"^([ABCD])\)\s*(.*)\s*$")
KEY_RE = re.compile(r"^(?P<id>[A-Z]{1,3}\d+-\d{3})\s*[-–—�]+\s*Correct:\s*(?P<correct>[ABCD])(?:\s*[-–—�]+\s*Explanation:\s*(?P<exp>.*))?\s*$")

def split_questions_and_key(lines):
    for i, line in enumerate(lines):
        if KEY_RE.match(line.strip()):
            return lines[:i], lines[i:]
    return lines, []

def parse_key_blocks(key_lines):
    key_map = {}
    cur_id = None
    cur_correct = None
    cur_exp_parts = []

    def flush():
        nonlocal cur_id, cur_correct, cur_exp_parts
        if cur_id:
            key_map[cur_id] = (cur_correct or "", " ".join(cur_exp_parts).strip())
        cur_id = None
        cur_correct = None
        cur_exp_parts = []

    for raw in key_lines:
        line = raw.strip()
        if not line:
            continue

        if line.lower().startswith("answer summary"):
            flush()
            break

        m = KEY_RE.match(line)
        if m:
            flush()
            cur_id = m.group("id").strip()
            cur_correct = m.group("correct").strip()
            exp = (m.group("exp") or "").strip()
            if exp:
                cur_exp_parts.append(exp)
            continue

        if cur_id:
            if line.lower().startswith("explanation:"):
                line = line.split(":", 1)[1].strip()
            if line:
                cur_exp_parts.append(line)

    flush()
    return key_map

def is_noise_header(line):
    l = line.strip().lower()
    return (
        not l
        or l.startswith("ibew aptitude test")
        or l.startswith("algebra and functions")
        or l.startswith("reading comprehension")
        or l.startswith("part a")
        or l.startswith("time limit")
    )

def parse_questions(q_lines):
    i = 0
    questions = []
    context_parts = []

    while i < len(q_lines):
        line = q_lines[i].rstrip("\n")
        stripped = line.strip()

        if ID_RE.match(stripped):
            qid = stripped
            i += 1

            prompt_parts = []

            while i < len(q_lines):
                l = q_lines[i].rstrip("\n")
                if OPT_RE.match(l.strip()):
                    break
                prompt_parts.append(l)
                i += 1

            if prompt_parts and prompt_parts[0].strip().lower().startswith(("prompt:", "question:")):
                prompt_parts[0] = prompt_parts[0].split(":", 1)[1].lstrip()

            question_text = "\n".join([p.rstrip() for p in prompt_parts]).strip()

            full_prompt_parts = []
            if context_parts:
                full_prompt_parts.extend(context_parts)
                full_prompt_parts.append("")
            full_prompt_parts.append(question_text)

            prompt = "\n".join(full_prompt_parts).strip()

            choices = {}
            for expected in ["A", "B", "C", "D"]:
                if i >= len(q_lines):
                    raise ValueError(f"Missing option {expected}) for {qid}")
                m = OPT_RE.match(q_lines[i].strip())
                if not m or m.group(1) != expected:
                    raise ValueError(f"Expected {expected}) for {qid}, got: {q_lines[i].strip()}")
                choices[expected] = m.group(2).strip()
                i += 1

            questions.append({"id": qid, "prompt": prompt, "choices": choices})
            continue

        if stripped.startswith("Passage "):
            context_parts = [stripped]
            i += 1
            while i < len(q_lines):
                nxt = q_lines[i].rstrip("\n")
                nxt_s = nxt.strip()
                if ID_RE.match(nxt_s) or nxt_s.startswith("Passage "):
                    break
                if nxt_s:
                    context_parts.append(nxt_s)
                i += 1
            continue

        if not context_parts and is_noise_header(stripped):
            i += 1
            continue

        i += 1

    return questions

def attach_answers(questions, key_map):
    missing_keys = []
    bad_letters = []
    out = []

    for q in questions:
        qid = q["id"]
        if qid not in key_map:
            missing_keys.append(qid)
            q["correct"] = ""
            q["explanation"] = ""
            out.append(q)
            continue

        correct, exp = key_map[qid]
        correct = correct.strip().upper()

        if correct not in q["choices"]:
            bad_letters.append((qid, correct))
            correct = "A"

        q["correct"] = correct
        q["explanation"] = exp
        out.append(q)

    return out, missing_keys, bad_letters

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", required=True)
    ap.add_argument("--outfile", required=True)
    ap.add_argument("--expected", type=int, default=None)
    args = ap.parse_args()

    txt = Path(args.infile).read_text(encoding="utf-8-sig", errors="replace")
    lines = txt.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    q_lines, key_lines = split_questions_and_key(lines)
    questions = parse_questions(q_lines)
    key_map = parse_key_blocks(key_lines)

    merged, missing_keys, bad_letters = attach_answers(questions, key_map)

    if args.expected is not None and len(merged) != args.expected:
        print(f"WARNING: expected {args.expected} questions, found {len(merged)}")

    if missing_keys:
        print("WARNING: Missing key entries for:", ", ".join(missing_keys[:20]), ("..." if len(missing_keys) > 20 else ""))

    if bad_letters:
        print("WARNING: Invalid answer letters:", bad_letters[:10])

    out_path = Path(args.outfile)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: wrote {len(merged)} questions to {out_path}")

if __name__ == "__main__":
    main()
