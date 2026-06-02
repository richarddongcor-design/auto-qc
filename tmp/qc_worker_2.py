#!/usr/bin/env python3
"""质检Worker脚本 - 逐条检查100条对话的13条规则"""

import json
import re

# Read the batch data
with open(r"C:\Users\dongyi\myprojects\auto-qc\tmp\worker_prompts\batch_2.txt", "r", encoding="utf-8") as f:
    raw = f.read()

# Parse conversations
conversations = []
blocks = raw.split("=== 对话 ")
for block in blocks[1:]:  # skip the prefix part
    lines = block.strip().split("\n")
    header = lines[0].strip()
    conv_id = header.split(" (意向:")[0].strip()
    turns = []
    for line in lines[1:]:
        line = line.strip()
        if line.startswith("AI: "):
            turns.append({"role": "AI", "text": line[4:]})
        elif line.startswith("用户: "):
            turns.append({"role": "用户", "text": line[4:]})
    conversations.append({"id": conv_id, "turns": turns})

print(f"Parsed {len(conversations)} conversations")

# Helper functions
def get_ai_turns(conv):
    return [t for t in conv["turns"] if t["role"] == "AI"]

def get_user_turns(conv):
    return [t for t in conv["turns"] if t["role"] == "用户"]

def has_user_said(conv, keywords):
    """Check if any user turn contains any of the keywords"""
    for t in get_user_turns(conv):
        for kw in keywords:
            if kw in t["text"]:
                return True
    return False

def find_user_turn_with(conv, keywords):
    """Find user turn that contains any keyword"""
    for t in get_user_turns(conv):
        for kw in keywords:
            if kw in t["text"]:
                return t
    return None

def find_ai_turn_after_user(conv, user_turn_idx, keywords=None):
    """Find the next AI turn after a specific user turn"""
    for i in range(user_turn_idx + 1, len(conv["turns"])):
        if conv["turns"][i]["role"] == "AI":
            if keywords is None:
                return conv["turns"][i]
            for kw in keywords:
                if kw in conv["turns"][i]["text"]:
                    return conv["turns"][i]
    return None

def has_garbled_text(text):
    """Check for garbled text patterns"""
    # Patterns like 哦/明白（那就) or missing spaces
    patterns = [
        r"哦/明白.*[（\(].*?\)",  # 哦/明白（那就)
        r"[）\)].*?再见",  # closing paren then goodbye
        r"哦/明白",
    ]
    for p in patterns:
        if re.search(p, text):
            return True
    return False

def count_confirm_questions(conv):
    """Count AI confirmation questions"""
    confirm_patterns = [
        "要不要接触", "是否还要接触", "要不要考虑", "您看可以吗",
        "您看行吗", "有兴趣", "愿意", "感兴趣吗", "接触一下",
        "让企业HR联系您", "先把您简历给企业HR", "这边让企业HR联系您",
    ]
    count = 0
    for t in get_ai_turns(conv):
        for p in confirm_patterns:
            if p in t["text"]:
                count += 1
                break
    return count

def check_signal_misjudgment(conv):
    """Check if AI says signal bad but user has been speaking"""
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "AI" and ("信号不太好" in t["text"] or "听不见您说话" in t["text"]):
            # Check previous 3 turns for user speaking
            for j in range(max(0, i - 3), i):
                if conv["turns"][j]["role"] == "用户" and "用户无应答" not in conv["turns"][j]["text"]:
                    return True, t
    return False, None

def check_company_location_mismatch(text):
    """Check if company name city differs from work location"""
    city_markers = ["北京", "上海", "广州", "深圳", "成都", "杭州", "重庆",
                    "武汉", "南京", "天津", "苏州", "西安", "青岛", "长沙",
                    "郑州", "济南", "大连", "沈阳", "哈尔滨", "福州", "厦门",
                    "合肥", "南昌", "昆明", "贵阳", "兰州", "太原", "石家庄",
                    "乌鲁木齐", "海口", "南宁", "宁波", "东莞", "佛山", "珠海"]

    # Find company name context
    company_match = re.search(r"这家企业是(.+?)。给到的岗位是", text)
    if not company_match:
        return None, None, None

    company_name = company_match.group(1)

    # Find location
    loc_match = re.search(r"工作地点在(.+?)(?:嗯|，|。)", text)
    if not loc_match:
        return None, None, None

    location = loc_match.group(1)

    # Extract city from company name (first city found)
    company_city = None
    for city in city_markers:
        if city in company_name:
            company_city = city
            break

    # Extract city from location
    loc_city = None
    for city in city_markers:
        if city in location:
            loc_city = city
            break

    if company_city and loc_city and company_city != loc_city:
        return company_name, company_city, loc_city

    return None, None, None

def check_r11_redundant_intro(conv):
    """Check R11: redundant company intro in adjacent turns"""
    ai_turns = get_ai_turns(conv)
    for i in range(len(ai_turns) - 1):
        current = ai_turns[i]["text"]
        next_turn = ai_turns[i + 1]["text"]
        # Check if current mentions helping a company with recruitment
        if "帮" in current and "做招聘" in current:
            # Check if next turn mentions the same company
            comp_match = re.search(r"帮(.+?)做招聘", current)
            if comp_match:
                company = comp_match.group(1)
                if company in next_turn:
                    return True, ai_turns[i], ai_turns[i + 1]
        # Also check for "这家企业是XX公司" followed by same company
        comp_match1 = re.search(r"这家企业是(.+?)。", current)
        comp_match2 = re.search(r"这家企业是(.+?)。", next_turn)
        if comp_match1 and comp_match2:
            if comp_match1.group(1) == comp_match2.group(1):
                return True, ai_turns[i], ai_turns[i + 1]
    return False, None, None

def check_r03_duplicate(conv):
    """Check R03: AI duplicate content"""
    ai_turns = get_ai_turns(conv)
    duplicates = []
    for i in range(len(ai_turns)):
        for j in range(i + 1, len(ai_turns)):
            t1 = ai_turns[i]["text"]
            t2 = ai_turns[j]["text"]
            # Normalize: remove TTS markers
            def normalize(t):
                t = re.sub(r"[./]", "", t)
                t = t.replace("呃", "").replace("嗯", "").replace("啊", "").replace("哦", "")
                return t.strip()
            n1 = normalize(t1)
            n2 = normalize(t2)
            if len(n1) > 20 and len(n2) > 20:
                if n1 == n2 or (len(n1) > 50 and n2 in n1) or (len(n2) > 50 and n1 in n2):
                    duplicates.append((ai_turns[i], ai_turns[j]))
    return duplicates

# Main analysis
results = []
spot_checks = []

# Define spot check IDs (random selection of conversations with interesting patterns)
spot_check_ids = set()
# We'll pick some at random after analysis

for conv in conversations:
    violations = []
    ai_turns = get_ai_turns(conv)
    user_turns = get_user_turns(conv)
    conv_id = conv["id"]

    # Skip conversations with no real interaction
    has_real_interaction = any("用户无应答" not in t["text"] and t["text"].strip() != "" for t in user_turns)

    # === R01: 无视用户明确拒绝 ===
    refusal_keywords = ["不考虑", "不需要", "不用了", "拜拜", "算了吧", "暂时不考虑", "没兴趣", "不用", "不要", "没意向"]
    user_refusal_idx = None
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "用户":
            for kw in refusal_keywords:
                if kw in t["text"]:
                    user_refusal_idx = i
                    break
        if user_refusal_idx is not None:
            break

    if user_refusal_idx is not None:
        # Check if AI continues with job intro or resume push after refusal
        for i in range(user_refusal_idx + 1, len(conv["turns"])):
            if conv["turns"][i]["role"] == "AI":
                ai_text = conv["turns"][i]["text"]
                if ("这家企业是" in ai_text or "给到的岗位是" in ai_text or
                    "要不要接触" in ai_text or "把您的简历" in ai_text or
                    "HR看一下" in ai_text or "是否还要接触" in ai_text or
                    "愿意和企业" in ai_text):
                    user_text = conv["turns"][user_refusal_idx]["text"]
                    violations.append({
                        "rule_id": "R01",
                        "rule_name": "无视用户明确拒绝",
                        "severity": "高",
                        "evidence": f"用户: {user_text} | AI: {ai_text}",
                        "suggestion": f"AI在用户明确说'{user_text[:20]}...'后应立即礼貌告别结束通话，不应继续播报岗位信息或推进简历流程"
                    })
                break  # only check first AI response after refusal

    # === R02: 对话未正常结束 ===
    if has_real_interaction and ai_turns:
        last_ai = ai_turns[-1]
        farewell_keywords = ["再见", "祝您", "不打扰", "生活愉快", "职场发展", "先不打扰"]
        has_farewell = any(kw in last_ai["text"] for kw in farewell_keywords)

        # Check if the conversation ended with the AI speaking (no user turn after)
        if conv["turns"][-1]["role"] == "AI" and not has_farewell:
            violations.append({
                "rule_id": "R02",
                "rule_name": "对话未正常结束",
                "severity": "高",
                "evidence": f"用户: {user_turns[-1]['text'] if user_turns else 'N/A'} | AI(最后): {last_ai['text']}",
                "suggestion": "AI在有实质性交互的对话结束时，应包含礼貌告别话术如'祝您生活愉快，再见'"
            })
        # Also check: AI ends with a question, then user says bye but AI doesn't respond with farewell
        # Check if last user turn has farewell but last AI turn doesn't have it
        if user_turns:
            last_user = user_turns[-1]
            user_has_bye = any(kw in last_user["text"] for kw in ["再见", "拜拜", "谢谢"])
            if user_has_bye and len(conv["turns"]) > 1:
                # Find last AI turn before the user's bye
                for i in range(len(conv["turns"]) - 1, -1, -1):
                    if conv["turns"][i]["role"] == "AI":
                        ai_before_bye = conv["turns"][i]
                        if not any(kw in ai_before_bye["text"] for kw in farewell_keywords):
                            # Only flag if user says bye to end the conversation
                            if last_user["text"] in ["再见", "好谢谢，好再见", "嗯，好"] or "再见" in last_user["text"]:
                                violations.append({
                                    "rule_id": "R02",
                                    "rule_name": "对话未正常结束",
                                    "severity": "高",
                                    "evidence": f"用户: {last_user['text']} | AI(最后): {last_ai['text']}",
                                    "suggestion": "用户已说再见，AI应回应礼貌告别而非追问问题"
                                })
                        break

    # === R03: AI内容重复播报 ===
    dup_pairs = check_r03_duplicate(conv)
    for t1, t2 in dup_pairs:
        text_preview = t1["text"][:60] + "..."
        violations.append({
            "rule_id": "R03",
            "rule_name": "AI内容重复播报",
            "severity": "高",
            "evidence": f"AI重复播报: {text_preview} | AI重复播报: {t2['text'][:60]}...",
            "suggestion": "AI应在同一通对话中避免输出相同内容，需维护对话状态防止重复播报"
        })

    # === R04: 公司名与工作地点矛盾 ===
    for t in ai_turns:
        comp_name, comp_city, loc_city = check_company_location_mismatch(t["text"])
        if comp_name and comp_city and loc_city:
            violations.append({
                "rule_id": "R04",
                "rule_name": "公司名与工作地点矛盾",
                "severity": "高",
                "evidence": f"AI: 公司名含'{comp_city}'({comp_name})但工作地点在'{loc_city}'",
                "suggestion": f"AI应区分说明公司注册地与实际工作地，避免'公司名含{comp_city}但地点在{loc_city}'的矛盾表述"
            })
            break  # only flag once per conversation

    # === R05: 回避用户问题不正面回答 ===
    question_keywords = ["什么", "怎么", "哪里", "为什么", "具体", "做什么", "哪个", "多少", "什么行业", "做什么产品"]
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "用户":
            has_question = any(kw in t["text"] for kw in question_keywords)
            if has_question:
                # Find next AI response
                for j in range(i + 1, len(conv["turns"])):
                    if conv["turns"][j]["role"] == "AI":
                        ai_resp = conv["turns"][j]["text"]
                        # Check if AI just deflects without substantive answer
                        deflect_patterns = ["您可以晚点详细看下", "在猎聘上", "给企业HR看一下", "稍后我把您的简历", "让HR"]
                        is_deflect = any(p in ai_resp for p in deflect_patterns)
                        # Check if AI provides any substantive info
                        has_substance = any(kw in ai_resp for kw in ["主营", "主要负责", "薪资是", "工作地点", "这家企业是", "公司叫"])

                        if is_deflect and not has_substance:
                            violations.append({
                                "rule_id": "R05",
                                "rule_name": "回避用户问题不正面回答",
                                "severity": "高",
                                "evidence": f"用户: {t['text']} | AI: {ai_resp}",
                                "suggestion": f"用户询问'{t['text'][:30]}...'，AI应正面解答疑问而非仅推给猎聘或HR"
                            })
                        elif is_deflect and has_substance:
                            # AI gave some info but also deflected - still might be R05 if the deflection is the main response
                            # Check if the substantive answer actually addresses the question
                            if "做什么" in t["text"] or "什么行业" in t["text"]:
                                if "主要负责" not in ai_resp and "主营" not in ai_resp:
                                    violations.append({
                                        "rule_id": "R05",
                                        "rule_name": "回避用户问题不正面回答",
                                        "severity": "高",
                                        "evidence": f"用户: {t['text']} | AI: {ai_resp}",
                                        "suggestion": f"用户询问公司业务/行业，AI应先介绍公司主营业务而非直接推给HR"
                                    })
                        break  # only check first AI response

    # === R06: 重复确认意向 ===
    confirm_count = count_confirm_questions(conv)
    if confirm_count >= 3:
        violations.append({
            "rule_id": "R06",
            "rule_name": "重复确认意向",
            "severity": "高",
            "evidence": f"AI在同一通对话中重复确认意向 {confirm_count} 次",
            "suggestion": f"AI重复确认意向达{confirm_count}次，应在用户已表态后直接推进下一步，而非反复追问同一问题"
        })

    # === R07: 无响应时循环追问 ===
    # Look for pattern: user silence -> AI asks/broadcasts -> user silence again -> AI continues
    consecutive_silence = 0
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "用户" and "用户无应答" in t["text"]:
            consecutive_silence += 1
            if consecutive_silence >= 2:
                # Check if there's an AI turn between these silences that continued broadcasting
                # Find the AI turn right before this silence
                for j in range(i - 1, -1, -1):
                    if conv["turns"][j]["role"] == "AI":
                        ai_text = conv["turns"][j]["text"]
                        if ("这家企业是" in ai_text or "要不要接触" in ai_text or
                            "是否还要接触" in ai_text or "岗位" in ai_text or
                            "您看" in ai_text):
                            violations.append({
                                "rule_id": "R07",
                                "rule_name": "无响应时循环追问",
                                "severity": "中",
                                "evidence": f"用户连续无应答后AI仍继续: {ai_text[:80]}...",
                                "suggestion": "用户连续无应答时，AI应在2次后礼貌结束通话，而非继续播报岗位信息或追问意向"
                            })
                        break
        else:
            if t["role"] == "用户":
                # Non-silence user response resets counter
                if t["text"].strip() and "用户无应答" not in t["text"]:
                    consecutive_silence = 0
            elif t["role"] == "AI":
                # AI turns don't break the silence count but we track if AI broadcasts during silence
                pass

    # === R08: 用户不便时未妥善处理 ===
    inconvenience_keywords = ["在忙", "开会", "开车", "不方便", "稍等", "等一下", "稍等一下", "有点忙"]
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "用户":
            has_inconvenience = any(kw in t["text"] for kw in inconvenience_keywords)
            if has_inconvenience:
                # Check if AI schedules a follow-up time
                for j in range(i + 1, len(conv["turns"])):
                    if conv["turns"][j]["role"] == "AI":
                        ai_text = conv["turns"][j]["text"]
                        # If AI continues with job intro or push without scheduling specific time
                        if ("这家企业是" in ai_text or "把您的简历" in ai_text or
                            "要不要接触" in ai_text or "介绍下企业" in ai_text):
                            violations.append({
                                "rule_id": "R08",
                                "rule_name": "用户不便时未妥善处理",
                                "severity": "中",
                                "evidence": f"用户: {t['text']} | AI: {ai_text}",
                                "suggestion": f"用户表示'{t['text'][:20]}...'，AI应主动结束通话并约定下次联系时间，而非继续追问或推进流程"
                            })
                        break

    # === R09: 误判用户信号 ===
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "AI" and ("信号不太好" in t["text"] or "听不见您说话" in t["text"]):
            # Check previous 3 turns for user actually speaking (not just silence)
            found_real_speech = False
            real_speech_turn = None
            for j in range(max(0, i - 3), i):
                if conv["turns"][j]["role"] == "用户":
                    user_text = conv["turns"][j]["text"]
                    # Check if user has any actual speech (not purely "用户无应答")
                    if user_text.strip() != "用户无应答" and user_text.replace("用户无应答", "").strip():
                        found_real_speech = True
                        real_speech_turn = conv["turns"][j]
                        break
            if found_real_speech:
                violations.append({
                    "rule_id": "R09",
                    "rule_name": "误判用户信号",
                    "severity": "中",
                    "evidence": f"AI: {t['text']} | 但此前用户有发言: {real_speech_turn['text'][:50]}",
                    "suggestion": "AI声称用户信号不好前应检查用户是否有实际发言，避免在有用户输入的情况下误判为信号问题"
                })

    # === R10: 结束话术出现乱码 ===
    for t in ai_turns:
        if has_garbled_text(t["text"]):
            violations.append({
                "rule_id": "R10",
                "rule_name": "结束话术出现乱码",
                "severity": "中",
                "evidence": f"AI: {t['text']}",
                "suggestion": "AI结束话术中出现全角半角括号混用、多余斜杠等乱码字符，应修复文本生成逻辑"
            })
            break

    # === R11: 公司自我介绍冗余重复 ===
    r11_found, t1, t2 = check_r11_redundant_intro(conv)
    if r11_found:
        violations.append({
            "rule_id": "R11",
            "rule_name": "公司自我介绍冗余重复",
            "severity": "中",
            "evidence": f"AI轮次1: {t1['text'][:80]}... | AI轮次2: {t2['text'][:80]}...",
            "suggestion": "AI不应在相邻两轮中对同一家公司重复介绍，应在说明身份后直接进入岗位介绍"
        })

    # === R12: 用户要在平台查看仍强推简历 ===
    platform_keywords = ["在平台上", "APP上看", "猎聘上", "平台上", "在APP上", "在猎聘", "平台上回复"]
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "用户":
            wants_platform = any(kw in t["text"] for kw in platform_keywords)
            if wants_platform:
                # Check if AI still pushes resume to HR
                for j in range(i + 1, len(conv["turns"])):
                    if conv["turns"][j]["role"] == "AI":
                        ai_resp = conv["turns"][j]["text"]
                        if "把您的简历" in ai_resp and "HR看一下" in ai_resp:
                            violations.append({
                                "rule_id": "R12",
                                "rule_name": "用户要在平台查看仍强推简历",
                                "severity": "中",
                                "evidence": f"用户: {t['text']} | AI: {ai_resp}",
                                "suggestion": f"用户表示想在平台查看，AI应尊重用户自主选择权，不应再推送'把简历给HR'的话术"
                            })
                        break

    # === R13: 用户同意后重复要简历 ===
    # Check if user explicitly agrees to contact, then AI asks for resume multiple times
    # or asks again with different wording after already asking once
    resume_ask_turns = []
    for i, t in enumerate(conv["turns"]):
        if t["role"] == "AI":
            if "把您的简历" in t["text"] or "先把您简历" in t["text"]:
                resume_ask_turns.append(i)

    if len(resume_ask_turns) >= 2:
        # Check if user agreed before the second resume ask
        user_agreed_before_second = False
        for turn_idx in conv["turns"]:
            if turn_idx["role"] == "用户":
                idx = conv["turns"].index(turn_idx)
                if resume_ask_turns[0] < idx < resume_ask_turns[1]:
                    if any(kw in turn_idx["text"] for kw in ["可以", "好的", "行", "没问题"]):
                        user_agreed_before_second = True
                        break

        # Also flag if user never explicitly agreed but AI asks resume 2+ times
        if not user_agreed_before_second:
            # Check if there was any user response between the two asks
            has_user_between = False
            for idx in range(resume_ask_turns[0] + 1, resume_ask_turns[1]):
                if conv["turns"][idx]["role"] == "用户":
                    has_user_between = True
                    break
            if has_user_between:
                user_agreed_before_second = True

        if user_agreed_before_second or len(resume_ask_turns) >= 2:
            # Build evidence from first two resume asks
            t_first = conv["turns"][resume_ask_turns[0]]
            t_second = conv["turns"][resume_ask_turns[1]]
            violations.append({
                "rule_id": "R13",
                "rule_name": "用户同意后重复要简历",
                "severity": "低",
                "evidence": f"AI第1次要简历: {t_first['text']} | AI第2次要简历: {t_second['text']}",
                "suggestion": "用户已明确同意或已有交互，AI不应再用不同话术重复询问是否可以把简历给HR"
            })

    # Build result
    if violations:
        results.append({
            "id": conv_id,
            "status": "violation",
            "violations": violations
        })
    else:
        results.append({
            "id": conv_id,
            "status": "pass",
            "violations": []
        })

# Generate spot check details for interesting conversations
spot_check_ids = ["11223268509", "11266880587", "11139337641", "11227742649", "11132359353"]

for sid in spot_check_ids:
    conv = next((c for c in conversations if c["id"] == sid), None)
    if conv is None:
        continue

    reasoning = f"【对话 {sid} 详细推理】\n"
    reasoning += f"该对话共{len(conv['turns'])}个轮次。\n"

    for rule_id in ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R13"]:
        # Re-check each rule for this conversation with reasoning
        ai_turns = get_ai_turns(conv)
        user_turns = get_user_turns(conv)
        result = next((r for r in results if r["id"] == sid), None)

        violated = any(v["rule_id"] == rule_id for v in (result["violations"] if result["status"] == "violation" else []))

        if rule_id == "R01":
            refusal = find_user_turn_with(conv, ["不考虑", "不需要", "不用了", "没兴趣", "不用"])
            if refusal:
                idx = conv["turns"].index(refusal)
                resp = find_ai_turn_after_user(conv, idx)
                reasoning += f"R01(无视拒绝): 用户在轮次{idx+1}说'{refusal['text'][:30]}...'，AI回应'{resp['text'][:50] if resp else '无'}...' -> {'违规' if violated else '不违规'}\n"
            else:
                reasoning += f"R01(无视拒绝): 对话中未检测到用户明确拒绝 -> 不违规\n"

        elif rule_id == "R02":
            last_ai = ai_turns[-1] if ai_turns else None
            if last_ai:
                has_bye = any(kw in last_ai["text"] for kw in ["再见", "祝您", "不打扰", "生活愉快"])
                reasoning += f"R02(未正常结束): AI最后发言是否含告别词={has_bye} -> {'违规' if violated else '不违规'}\n"
            else:
                reasoning += f"R02(未正常结束): 无AI发言 -> 不违规\n"

        elif rule_id == "R03":
            reasoning += f"R03(内容重复): 检查AI各轮次发言是否高度相似 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R04":
            reasoning += f"R04(公司地点矛盾): 检查公司名城市与工作地点是否一致 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R05":
            reasoning += f"R05(回避问题): 检查用户提问后AI是否正面回答 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R06":
            cc = count_confirm_questions(conv)
            reasoning += f"R06(重复确认): AI确认意向次数={cc}，阈值>=3 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R07":
            reasoning += f"R07(无响应循环): 检查连续沉默后AI是否继续追问 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R08":
            reasoning += f"R08(用户不便): 检查用户表示不便时AI是否约时间 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R09":
            reasoning += f"R09(信号误判): 检查AI说信号不好时用户是否有发言 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R10":
            reasoning += f"R10(结束乱码): 检查结束话术是否有乱码字符 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R11":
            reasoning += f"R11(冗余介绍): 检查相邻轮次是否重复介绍同一公司 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R12":
            reasoning += f"R12(强推简历): 检查用户要看平台时AI是否仍推简历 -> {'违规' if violated else '不违规'}\n"

        elif rule_id == "R13":
            reasoning += f"R13(重复要简历): 检查用户同意后AI是否再次要简历 -> {'违规' if violated else '不违规'}\n"

    spot_checks.append({"id": sid, "reasoning": reasoning})

# Build final output
output = {
    "batch_id": 2,
    "rules_checked": ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R13"],
    "spot_check_details": spot_checks,
    "results": results
}

# Write output
with open(r"C:\Users\dongyi\myprojects\auto-qc\tmp\batch_result_2.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Print summary
total = len(results)
passed = sum(1 for r in results if r["status"] == "pass")
failed = total - passed
violation_counts = {}
for r in results:
    if r["status"] == "violation":
        for v in r["violations"]:
            rid = v["rule_id"]
            violation_counts[rid] = violation_counts.get(rid, 0) + 1

print(f"\nTotal: {total}, Passed: {passed}, Violations: {failed}")
print(f"\nViolation counts by rule:")
for rid, cnt in sorted(violation_counts.items()):
    print(f"  {rid}: {cnt}")

print(f"\nSpot check details: {len(spot_checks)}")
print(f"\nOutput written to: C:\\Users\\dongyi\\myprojects\\auto-qc\\tmp\\batch_result_2.json")
