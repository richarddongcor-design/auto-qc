import json
import re

with open(r"C:/Users/dongyi/.claude/skills/auto-qc/tmp/batches/batch_1_prompt.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Extract conversations
start = content.index('[\n  {\n    "id":')
bracket_count = 0
end = start
for i, c in enumerate(content[start:]):
    if c == '[':
        bracket_count += 1
    elif c == ']':
        bracket_count -= 1
        if bracket_count == 0:
            end = start + i + 1
            break

conversations = json.loads(content[start:end])
print(f"Total conversations: {len(conversations)}")

# For each conversation, print it for manual review
for idx, conv in enumerate(conversations):
    cid = conv["id"]
    intent = conv["intent"]
    conv_text = conv["conversation"]
    
    # Parse turns
    turns = []
    for line in conv_text.split("\n"):
        line = line.strip()
        if line.startswith("AI: "):
            turns.append(("AI", line[4:]))
        elif line.startswith("用户: "):
            turns.append(("USER", line[4:]))
    
    # Check RULE-001: User refuses, AI keeps pushing
    refuse_keywords = ["不用了", "不需要", "不考虑", "不考虑了", "暂时不用", "挂了吧", "暂时不需要", "没有", "没有了", "算了", "不感兴趣", "拜拜", "没兴趣", "不需要了", "不考虑了啊"]
    
    # Check RULE-002: AI repeats same/similar speech
    ai_turns = [t[1] for t in turns if t[0] == "AI"]
    
    # Check RULE-003: User raises concern, AI ignores and pushes
    concern_keywords = ["什么产品", "做什么", "干什么", "在哪", "在哪里", "距离", "太远", "薪资", "工资", "产品", "行业", "做什么的", "产品是做哪一块", "自己开发的平台", "具体做什么", "做什么行业"]
    
    flags = []
    
    # R01 check
    for i, (speaker, text) in enumerate(turns):
        if speaker == "USER":
            for kw in refuse_keywords:
                if kw in text:
                    # Check if next AI turn pushes forward
                    for j in range(i+1, len(turns)):
                        if turns[j][0] == "AI":
                            ai_resp = turns[j][1]
                            if any(push in ai_resp for push in ["简历", "HR", "投递", "接触", "介绍", "这样的", "岗位是"]):
                                flags.append(f"R01: User said '{text[:30]}...' (contains '{kw}'), AI replied '{ai_resp[:50]}...'")
                            else:
                                pass  # AI accepted refusal
                            break
    
    # R02 check
    for i in range(len(ai_turns)):
        for j in range(i+1, len(ai_turns)):
            a, b = ai_turns[i], ai_turns[j]
            # Check exact match or very high similarity
            if a == b:
                flags.append(f"R02: Exact repeat between AI turn {i+1} and {j+1}: '{a[:60]}...'")
            elif len(a) > 30 and len(b) > 30:
                # Check if one is substring of other or very similar
                shorter = min(a, b, key=len)
                longer = max(a, b, key=len)
                if shorter in longer:
                    flags.append(f"R02: Substring repeat between AI turn {i+1} and {j+1}: '{shorter[:60]}...'")
    
    # R03 check - user asks about something specific, AI doesn't answer and pushes
    for i, (speaker, text) in enumerate(turns):
        if speaker == "USER":
            for kw in concern_keywords:
                if kw in text:
                    # Find next AI response
                    for j in range(i+1, len(turns)):
                        if turns[j][0] == "AI":
                            ai_resp = turns[j][1]
                            # Check if AI addresses the concern
                            ai_lower = ai_resp.lower()
                            # Check if AI just pushes forward without answering
                            if kw in ["产品", "做什么", "干什么", "行业", "做什么的", "产品是做哪一块", "具体做什么", "做什么行业"]:
                                if "产品" not in ai_resp and "行业" not in ai_resp and "做" not in ai_resp and "主营" not in ai_resp and "业务" not in ai_resp:
                                    if any(push in ai_resp for push in ["简历", "HR", "投递"]):
                                        flags.append(f"R03: User asked '{text[:40]}' (contains '{kw}'), AI replied '{ai_resp[:60]}...' without answering")
                            elif kw in ["在哪", "在哪里", "距离", "太远"]:
                                if "地址" not in ai_resp and "地点" not in ai_resp and "位置" not in ai_resp and "区" not in ai_resp:
                                    if any(push in ai_resp for push in ["简历", "HR", "投递"]):
                                        flags.append(f"R03: User asked '{text[:40]}' (contains '{kw}'), AI replied '{ai_resp[:60]}' without answering")
                            elif kw in ["薪资", "工资"]:
                                if "薪资" not in ai_resp and "工资" not in ai_resp and "k" not in ai_resp and "薪" not in ai_resp and "待遇" not in ai_resp:
                                    flags.append(f"R03: User asked '{text[:40]}' (contains '{kw}'), AI replied '{ai_resp[:60]}' without answering")
                            elif kw in ["自己开发的平台"]:
                                if "平台" not in ai_resp and "开发" not in ai_resp and "自己" not in ai_resp:
                                    if any(push in ai_resp for push in ["简历", "HR", "投递"]):
                                        flags.append(f"R03: User asked '{text[:40]}' (contains '{kw}'), AI replied '{ai_resp[:60]}' without answering")
                            break
    
    if flags:
        print(f"\n=== ID: {cid}, Intent: {intent} ===")
        for f in flags:
            print(f"  {f}")

