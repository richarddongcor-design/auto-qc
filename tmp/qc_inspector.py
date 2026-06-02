"""Quality inspector: checks all conversations against 13 quality rules."""
import json
import re
import os

BASE = "C:/Users/dongyi/myprojects/auto-qc"
BATCH_DIR = os.path.join(BASE, "tmp", "test_batches")

# Load all conversations
all_conversations = []
for i in range(1, 6):
    path = os.path.join(BATCH_DIR, f"batch_{i}.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["conversations"]:
        c["_batch"] = i
        all_conversations.append(c)

print(f"Loaded {len(all_conversations)} total conversations")

# Parse each conversation into turns
def parse_turns(conv_text):
    """Parse conversation text into list of (speaker, text) tuples."""
    turns = []
    # Split on AI: or 用户: but keep the delimiter
    parts = re.split(r'((?:AI|用户): )', conv_text)
    current_speaker = None
    current_text = []
    for part in parts:
        if part == "AI: ":
            if current_speaker:
                turns.append((current_speaker, "".join(current_text).strip()))
            current_speaker = "AI"
            current_text = []
        elif part == "用户: ":
            if current_speaker:
                turns.append((current_speaker, "".join(current_text).strip()))
            current_speaker = "用户"
            current_text = []
        else:
            current_text.append(part)
    if current_speaker:
        turns.append((current_speaker, "".join(current_text).strip()))
    return turns

# Helper: check if text contains any keyword
def has_any(text, keywords):
    return any(kw in text for kw in keywords)

# Helper: get AI turns
def ai_turns(turns):
    return [t for t in turns if t[0] == "AI"]

def user_turns(turns):
    return [t for t in turns if t[0] == "用户"]

def has_substantive_user(turns):
    """User has actual response beyond 无应答."""
    for sp, txt in user_turns(turns):
        if txt and "用户无应答" not in txt and txt.strip():
            return True
    return False

# ============ RULE CHECKS ============

results = []

for c in all_conversations:
    cid = c["id"]
    conv = c["conversation"]
    batch = c["_batch"]
    turns = parse_turns(conv)
    ai = ai_turns(turns)
    usr = user_turns(turns)

    flags = []

    # R01: 无视用户明确拒绝
    refuse_kw = ["不考虑", "不需要", "不用了", "拜拜", "算了吧", "暂时不考虑", "不考虑了", "没有兴趣"]
    push_kw = ["这家企业是", "给到的岗位是", "把您的简历", "要不要接触", "是否考虑", "要不要考虑", "您看呃就是要不要"]
    for i, (sp, txt) in enumerate(turns):
        if sp == "用户" and has_any(txt, refuse_kw):
            # Check next AI turn
            for j in range(i+1, len(turns)):
                if turns[j][0] == "AI":
                    next_ai = turns[j][1]
                    if has_any(next_ai, push_kw):
                        flags.append("R01")
                    break

    # R02: 对话未正常结束
    if has_substantive_user(turns) and ai:
        last_ai = ai[-1][1]
        farewell_kw = ["再见", "祝您", "不打扰", "生活愉快", "打扰您了"]
        if not has_any(last_ai, farewell_kw):
            flags.append("R02")

    # R03: AI内容重复播报
    ai_texts = [t[1] for t in ai if t[1] and "用户无应答" not in t[1]]
    # Clean TTS artifacts for comparison
    def clean_ai(t):
        t = re.sub(r'[./,，。、；;！!？?\s]', '', t)
        return t
    cleaned = [clean_ai(t) for t in ai_texts]
    for i in range(len(cleaned)):
        for j in range(i+1, len(cleaned)):
            if len(cleaned[i]) > 30 and len(cleaned[j]) > 30:
                # Check exact match after cleaning or high overlap
                if cleaned[i] == cleaned[j]:
                    flags.append("R03")
                    break
                # Check if one contains the other (>90% of shorter)
                shorter = min(cleaned[i], cleaned[j], key=len)
                longer = max(cleaned[i], cleaned[j], key=len)
                if shorter in longer and len(shorter) > len(longer) * 0.85:
                    flags.append("R03")
                    break
        if "R03" in flags:
            break

    # R04: 公司名与工作地点矛盾
    city_map = {
        "北京": "北京", "上海": "上海", "广州": "广州", "深圳": "深圳",
        "成都": "成都", "杭州": "杭州", "南京": "南京", "武汉": "武汉",
        "苏州": "苏州", "西安": "西安", "重庆": "重庆", "天津": "天津",
        "长沙": "长沙", "青岛": "青岛", "大连": "大连", "厦门": "厦门",
        "昆明": "昆明", "郑州": "郑州", "济南": "济南", "合肥": "合肥",
        "佛山": "佛山", "东莞": "东莞", "无锡": "无锡", "宁波": "宁波",
        "中山": "中山", "惠州": "惠州", "石家庄": "石家庄", "哈尔滨": "哈尔滨",
    }
    for _, txt in ai:
        # Extract company name
        m = re.search(r'(?:这家企业是|帮)(.+?)(?:。|做招聘)', txt)
        if m:
            company = m.group(1)
            # Extract location
            lm = re.search(r'工作地点在(\S+?)(?:嗯|，|。|、)', txt)
            if lm:
                location = lm.group(1)
                # Find city in company name
                company_city = None
                for city in city_map:
                    if city in company:
                        company_city = city
                        break
                if company_city:
                    # Check if location city matches
                    loc_city = None
                    for city in city_map:
                        if city in location:
                            loc_city = city
                            break
                    if loc_city and company_city != loc_city:
                        flags.append("R04")
                        break
        if "R04" in flags:
            break

    # R05: 回避用户问题不正面回答
    question_kw = ["什么", "怎么", "哪里", "为什么", "具体", "做什么", "哪一块", "产品", "行业", "薪资", "工资", "多少"]
    dodge_kw = ["晚点.*看", "猎聘.*发", "HR.*联系", "岗位细节", "让HR", "企业HR", "猎聘上"]
    for i, (sp, txt) in enumerate(turns):
        if sp == "用户" and has_any(txt, question_kw):
            # Check next AI turn
            for j in range(i+1, len(turns)):
                if turns[j][0] == "AI":
                    next_ai = turns[j][1]
                    if has_any(next_ai, dodge_kw):
                        # Check if AI gives any substantive info
                        no_substance = True
                        for info_kw in ["主营", "主要负责", "负责", "主要从事", "是一家"]:
                            if info_kw in next_ai:
                                no_substance = False
                                break
                        if no_substance:
                            flags.append("R05")
                    break

    # R06: 重复确认意向 (3+ times)
    confirm_kw = ["要不要接触", "是否还要接触", "是否考虑", "您看可以吗", "您看行吗",
                  "要不要考虑接触", "考虑接触一下", "您看呃就是要不要", "有兴趣.*接触",
                  "是否.*接触", "还要接触"]
    confirm_count = 0
    for _, txt in ai:
        if has_any(txt, confirm_kw):
            confirm_count += 1
    if confirm_count >= 3:
        flags.append("R06")

    # R07: 无响应时循环追问
    # Check for consecutive user no-response followed by AI continuing
    silence_count = 0
    silence_ai_count = 0
    for sp, txt in turns:
        if sp == "用户" and ("用户无应答" in txt or not txt.strip()):
            silence_count += 1
            if silence_count >= 2:
                silence_ai_count += 1
        else:
            silence_count = 0
    if silence_ai_count >= 2:
        flags.append("R07")

    # R08: 用户不便时未妥善处理
    busy_kw = ["开会", "在忙", "不方便", "在开车", "稍等", "等一下", "不太方便", "在外面", "在忙", "有点事"]
    for i, (sp, txt) in enumerate(turns):
        if sp == "用户" and has_any(txt, busy_kw):
            # Check if AI sets a follow-up time
            for j in range(i+1, len(turns)):
                if turns[j][0] == "AI":
                    next_ai = turns[j][1]
                    followup_kw = ["下次", "下次联系", "再联系", "约个时间", "约定", "方便.*再", "回去.*看"]
                    if not has_any(next_ai, followup_kw):
                        flags.append("R08")
                    break

    # R09: 误判用户信号
    signal_kw = ["信号不太好", "听不见您说话", "听不见"]
    for i, (sp, txt) in enumerate(turns):
        if sp == "AI" and has_any(txt, signal_kw):
            # Check nearby turns for user speech
            has_nearby_user = False
            for j in range(max(0, i-3), min(len(turns), i+4)):
                if turns[j][0] == "用户":
                    utxt = turns[j][1]
                    if utxt and "用户无应答" not in utxt and utxt.strip():
                        has_nearby_user = True
                        break
            if has_nearby_user:
                flags.append("R09")

    # R10: 结束话术出现乱码
    garbled_patterns = [
        r'[（(].*?[）)]',  # mismatched brackets like （那就) or (那就）
        r'哦/明白',  # slash in closing
        r'[，,][，,]',  # double commas
        r'再见[；;]',  # semicolon after 再见
        r'[，,]您看可以[吗呢]',  # missing space pattern
    ]
    for _, txt in ai:
        if len(txt) < 5:
            continue
        for pat in garbled_patterns:
            if re.search(pat, txt):
                flags.append("R10")
                break
        if "R10" in flags:
            break

    # R11: 公司自我介绍冗余重复
    for i in range(len(ai) - 1):
        txt1 = ai[i][1]
        txt2 = ai[i+1][1]
        if "帮" in txt1 and "做招聘" in txt1 and "这家企业是" in txt2:
            # Extract company from both
            m1 = re.search(r'帮(.+?)做招聘', txt1)
            m2 = re.search(r'这家企业是(.+?)(?:。|给到的)', txt2)
            if m1 and m2:
                comp1 = m1.group(1).strip()
                comp2 = m2.group(1).strip()
                if comp1 == comp2:
                    flags.append("R11")
                    break

    # R12: 用户要在平台查看仍强推简历
    platform_kw = ["平台上", "APP上", "APP上", "猎聘上", "猎聘上面", "在APP", "平台上", "分享JD", "JD", "在上面回复"]
    push_resume_kw = ["把您的简历", "简历给", "给企业HR", "HR看一下"]
    for i, (sp, txt) in enumerate(turns):
        if sp == "用户" and has_any(txt, platform_kw):
            # Check next AI turn
            for j in range(i+1, len(turns)):
                if turns[j][0] == "AI":
                    next_ai = turns[j][1]
                    if has_any(next_ai, push_resume_kw):
                        flags.append("R12")
                    break

    # R13: 用户同意后重复要简历
    agree_kw = ["可以", "好的", "好", "行", "嗯，可以", "嗯行", "同意", "没问题"]
    resume_kw = ["把您的简历", "简历给", "给企业HR", "要么.*简历", "先把您简历"]
    agreement_turns = []
    resume_request_turns = []
    for idx, (sp, txt) in enumerate(turns):
        if sp == "用户" and has_any(txt, agree_kw) and len(txt) < 15:
            agreement_turns.append(idx)
        if sp == "AI" and has_any(txt, resume_kw):
            resume_request_turns.append(idx)

    # If user agrees and AI asks about resume more than once after agreement
    if agreement_turns and len(resume_request_turns) >= 2:
        # Check if at least 2 resume requests happen after first agreement
        first_agree = agreement_turns[0]
        after_agree = [r for r in resume_request_turns if r > first_agree]
        if len(after_agree) >= 2:
            flags.append("R13")

    if flags:
        results.append({
            "id": cid,
            "batch": batch,
            "intent": c.get("intent", ""),
            "flags": sorted(set(flags)),
            "flag_count": len(set(flags))
        })

# Output summary
print(f"\nTotal flagged: {len(results)} / {len(all_conversations)}")

# Count by rule
from collections import Counter
rule_counts = Counter()
for r in results:
    for f in r["flags"]:
        rule_counts[f] += 1

print("\nRule hit counts:")
for rule in sorted(rule_counts.keys()):
    print(f"  {rule}: {rule_counts[rule]}")

# Output JSON
output = {
    "total_conversations": len(all_conversations),
    "flagged_count": len(results),
    "rule_counts": dict(rule_counts),
    "flagged_conversations": results
}

output_path = os.path.join(BASE, "tmp", "qc_inspection_results.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nResults saved to {output_path}")

# Print first 20 flagged for review
print("\n--- Flagged conversations (first 20) ---")
for r in results[:20]:
    print(f"  [{r['id']}] batch={r['batch']} intent={r['intent']} flags={r['flags']}")
