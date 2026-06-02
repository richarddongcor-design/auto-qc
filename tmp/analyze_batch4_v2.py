import re, json

with open('C:/Users/dongyi/myprojects/auto-qc/tmp/worker_prompts/batch_4.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

conversations = []
blocks = raw.split('=== ')
for block in blocks[1:]:
    lines = block.strip().split('\n')
    header = lines[0]
    conv_id = header.split('(')[0].strip().replace('对话', '').strip()
    intent_match = re.search(r'意向:\s*(\w+)', header)
    intent = intent_match.group(1) if intent_match else ''
    turns = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('AI:'):
            turns.append({'speaker': 'AI', 'text': line[3:].strip()})
        elif line.startswith('用户:'):
            turns.append({'speaker': '用户', 'text': line[3:].strip()})
    conversations.append({'id': conv_id, 'intent': intent, 'turns': turns})

city_names = ['北京','上海','广州','深圳','成都','杭州','南京','武汉','重庆','天津','苏州','西安','长沙','郑州','济南','青岛','大连','沈阳','哈尔滨','长春','合肥','福州','厦门','南昌','昆明','贵阳','南宁','海口','兰州','银川','西宁','乌鲁木齐','呼和浩特','太原','石家庄']

def user_has_substantial_response(conv):
    for t in conv['turns']:
        if t['speaker'] == '用户' and t['text'] != '用户无应答' and len(t['text'].strip()) > 2:
            return True
    return False

def last_ai_turn(conv):
    for t in reversed(conv['turns']):
        if t['speaker'] == 'AI':
            return t['text']
    return ''

def get_user_texts(conv):
    return [t['text'] for t in conv['turns'] if t['speaker'] == '用户']

def get_ai_texts(conv):
    return [t['text'] for t in conv['turns'] if t['speaker'] == 'AI']

def extract_company(text):
    m = re.search(r'这家企业是([^。,./\n]+)', text)
    if m:
        return m.group(1).strip()
    return ''

def extract_location(text):
    m = re.search(r'工作地点在([^嗯。，.\n]+)', text)
    if m:
        return m.group(1).strip()
    return ''

def check_r10(text):
    if not text:
        return False
    if '（那就)' in text:
        return True
    if '(那就)' in text and '/明白' in text:
        return True
    if '/明白（' in text and '那就)' in text:
        return True
    return False

results = []
for conv in conversations:
    cid = conv['id']
    turns = conv['turns']
    violations = []
    ai_texts = get_ai_texts(conv)
    user_texts = get_user_texts(conv)

    # R01: 无视用户明确拒绝 (deduplicated - only first match)
    refuse_patterns = ['不考虑','不需要','不用了','拜拜','算了吧','暂时不考虑','先不考虑','不考虑了','不用考虑','暂时不用','就不考虑','我算了']
    r01_found = False
    for i, t in enumerate(turns):
        if r01_found:
            break
        if t['speaker'] == '用户':
            txt = t['text']
            matched_pat = None
            for pat in refuse_patterns:
                if pat in txt:
                    matched_pat = pat
                    break
            if matched_pat:
                for j in range(i+1, len(turns)):
                    if turns[j]['speaker'] == 'AI':
                        ai_resp = turns[j]['text']
                        if ('这家企业是' in ai_resp or '岗位是' in ai_resp or '要不要接触' in ai_resp or '简历' in ai_resp or '给企业HR' in ai_resp):
                            violations.append({
                                'rule_id': 'R01',
                                'rule_name': '无视用户明确拒绝',
                                'severity': '高',
                                'evidence': '用户: ' + txt + ' | AI: ' + ai_resp,
                                'suggestion': 'AI在用户明确表达"'+ matched_pat +'"的拒绝意愿后，应立即礼貌结束对话并告别，而非继续播报岗位信息、追问是否接触或推进要简历流程。'
                            })
                            r01_found = True
                        break

    # R02: 对话未正常结束
    # Only flag if: user had substantial response, AI last turn has no farewell,
    # AND AI last turn does NOT end with a question (waiting for reply is not "abnormal ending")
    if user_has_substantial_response(conv):
        last_ai = last_ai_turn(conv)
        farewell_keywords = ['再见','祝您','不打扰','您先忙']
        has_farewell = any(kw in last_ai for kw in farewell_keywords)
        # If AI is waiting for reply (ends with ? or 呢？), not flagged as R02
        ends_with_question = last_ai.endswith('？') or last_ai.endswith('?') or last_ai.endswith('呢？')
        if last_ai and not has_farewell and not ends_with_question and len(last_ai) > 10 and '您是' not in last_ai:
            violations.append({
                'rule_id': 'R02',
                'rule_name': '对话未正常结束',
                'severity': '高',
                'evidence': '用户: ' + (user_texts[-1] if user_texts else '无') + ' | AI: ' + last_ai,
                'suggestion': 'AI在最后一条发言中应包含礼貌告别话术（如再见、祝您生活愉快等），而非以陈述或等待用户说话的方式结束。'
            })

    # R03: AI内容重复播报
    cleaned_ai = []
    for t in ai_texts:
        cleaned = re.sub(r'[/,./，。！？\s]', '', t)
        cleaned_ai.append((t, cleaned))
    r03_found = False
    for i in range(len(cleaned_ai)):
        if r03_found:
            break
        for j in range(i+1, len(cleaned_ai)):
            t1, c1 = cleaned_ai[i]
            t2, c2 = cleaned_ai[j]
            if c1 and c2 and len(c1) > 20:
                if c1 == c2:
                    violations.append({
                        'rule_id': 'R03',
                        'rule_name': 'AI内容重复播报',
                        'severity': '高',
                        'evidence': 'AI重复: ' + t1[:80] + ' | ' + t2[:80],
                        'suggestion': 'AI在同一通对话中重复播报了完全相同或高度相似的发言内容，应修复对话状态机避免同一响应被触发多次。'
                    })
                    r03_found = True
                    break

    # R04: 公司名与工作地点矛盾
    r04_found = False
    for t in turns:
        if r04_found:
            break
        if t['speaker'] == 'AI' and '这家企业是' in t['text']:
            company = extract_company(t['text'])
            location = extract_location(t['text'])
            if company and location:
                company_city = None
                for city in city_names:
                    if city in company:
                        company_city = city
                        break
                if company_city:
                    loc_city = None
                    for city in city_names:
                        if city in location:
                            loc_city = city
                            break
                    if loc_city and company_city != loc_city:
                        violations.append({
                            'rule_id': 'R04',
                            'rule_name': '公司名与工作地点矛盾',
                            'severity': '高',
                            'evidence': 'AI: 公司名含' + company_city + ' (' + company + ') 但工作地点在' + location,
                            'suggestion': 'AI播报时公司名包含城市标识但与实际工作地点不一致，应区分说明公司注册地与实际工作地。'
                        })
                        r04_found = True

    # R05: 回避用户问题不正面回答
    r05_found = False
    for i, t in enumerate(turns):
        if r05_found:
            break
        if t['speaker'] == '用户':
            txt = t['text']
            asks_detail = any(kw in txt for kw in ['做什么产品','做什么的','做啥的','具体做什么','什么类型','多少人的公司','多大规模','以什么为主','具体聊'])
            if asks_detail or ('什么' in txt and len(txt) > 5):
                for j in range(i+1, len(turns)):
                    if turns[j]['speaker'] == 'AI':
                        ai_resp = turns[j]['text']
                        is_dodge = any(d in ai_resp for d in ['晚点','HR联系','给企业HR','您可以晚点','岗位细节','在猎聘上查看'])
                        provides_info = any(kw in ai_resp for kw in ['专注','主营','致力于','业务包括','是叫','公司是'])
                        if is_dodge and not provides_info:
                            violations.append({
                                'rule_id': 'R05',
                                'rule_name': '回避用户问题不正面回答',
                                'severity': '高',
                                'evidence': '用户: ' + txt + ' | AI: ' + ai_resp,
                                'suggestion': 'AI在用户追问岗位/公司具体信息时，未给出实质性回答，仅用推给HR或猎聘的话术搪塞，应正面解答用户疑问。'
                            })
                            r05_found = True
                        break

    # R06: 重复确认意向
    confirm_patterns = ['要不要接触','是否还要接触','愿意接触','您看可以吗','您看行吗','详细沟通下怎么样','有兴趣接触','有兴趣跟企业','您看您愿意','您这边有兴趣']
    confirm_count = 0
    confirm_examples = []
    for t in ai_texts:
        for pat in confirm_patterns:
            if pat in t:
                confirm_count += 1
                confirm_examples.append(t[:50])
                break
    if confirm_count >= 3:
        violations.append({
            'rule_id': 'R06',
            'rule_name': '重复确认意向',
            'severity': '高',
            'evidence': 'AI在对话中' + str(confirm_count) + '次重复确认意向: ' + '; '.join(confirm_examples[:3]),
            'suggestion': 'AI在同一通对话中' + str(confirm_count) + '次重复确认意向（超过2次阈值），应在用户已表态后推进到下一步，而非反复追问。'
        })

    # R07: 无响应时循环追问
    user_no_response_streak = 0
    found_r07 = False
    for i, t in enumerate(turns):
        if found_r07:
            break
        if t['speaker'] == '用户' and t['text'].strip() == '用户无应答':
            user_no_response_streak += 1
        else:
            if t['speaker'] == 'AI' and user_no_response_streak >= 2:
                if '这家企业是' in t['text'] or '要不要接触' in t['text'] or '岗位' in t['text'] or '您看' in t['text']:
                    violations.append({
                        'rule_id': 'R07',
                        'rule_name': '无响应时循环追问',
                        'severity': '中',
                        'evidence': 'AI在连续' + str(user_no_response_streak) + '次用户无应答后继续播报: ' + t['text'][:80],
                        'suggestion': 'AI在用户连续' + str(user_no_response_streak) + '次无应答后仍继续播报岗位信息或追问意向，应在2次无回应后礼貌结束通话。'
                    })
                    found_r07 = True
            user_no_response_streak = 0

    # R08: 用户不便时未妥善处理
    # Only flag for genuine inconvenience (开会/不方便/在忙), not "等一下去看"
    found_r08 = False
    for i, t in enumerate(turns):
        if found_r08:
            break
        if t['speaker'] == '用户':
            txt = t['text']
            # More specific patterns for genuine inconvenience
            is_inconvenient = False
            if '开会' in txt:
                is_inconvenient = True
            if '不方便' in txt:
                is_inconvenient = True
            if '在忙' in txt and '看一下' not in txt:
                is_inconvenient = True
            if '我现在在忙' in txt:
                is_inconvenient = True
            if '我现在不太方便' in txt:
                is_inconvenient = True
            if '还在忙' in txt:
                is_inconvenient = True

            if is_inconvenient:
                for j in range(i+1, len(turns)):
                    if turns[j]['speaker'] == 'AI':
                        ai_resp = turns[j]['text']
                        has_followup = bool(re.search(r'(明天|后天|下周|改天|下午|上午).*联系', ai_resp))
                        if not has_followup:
                            violations.append({
                                'rule_id': 'R08',
                                'rule_name': '用户不便时未妥善处理',
                                'severity': '中',
                                'evidence': '用户: ' + txt + ' | AI: ' + ai_resp,
                                'suggestion': 'AI在用户表示不便时，未主动约定下次联系时间，应提出具体时间如"那我明天再联系您"。'
                            })
                            found_r08 = True
                        break

    # R09: 误判用户信号
    found_r09 = False
    for i, t in enumerate(turns):
        if found_r09:
            break
        if t['speaker'] == 'AI' and ('信号不太好' in t['text'] or '听不见您说话' in t['text']):
            has_user_response = False
            for k in range(max(0, i-6), min(len(turns), i+6)):
                if turns[k]['speaker'] == '用户' and turns[k]['text'].strip() != '用户无应答':
                    has_user_response = True
                    break
            if has_user_response:
                violations.append({
                    'rule_id': 'R09',
                    'rule_name': '误判用户信号',
                    'severity': '中',
                    'evidence': 'AI: ' + t['text'] + ' | 前后轮次用户有实际发言',
                    'suggestion': 'AI在判断用户信号不好之前，应先确认用户最近几轮是否有实际发言，避免误判。'
                })
                found_r09 = True

    # R10: 结束话术出现乱码
    found_r10 = False
    for t in ai_texts:
        if found_r10:
            break
        if ('明白' in t or '哦/' in t) and ('再见' in t or '联系您' in t):
            if check_r10(t):
                violations.append({
                    'rule_id': 'R10',
                    'rule_name': '结束话术出现乱码',
                    'severity': '中',
                    'evidence': 'AI: ' + t,
                    'suggestion': 'AI的结束话术中存在括号全角半角混用等异常字符，应统一为规范中文标点格式。'
                })
                found_r10 = True

    # R11: 公司自我介绍冗余重复
    found_r11 = False
    for i in range(len(turns)-1):
        if found_r11:
            break
        if turns[i]['speaker'] == 'AI' and turns[i+1]['speaker'] == 'AI':
            c1 = extract_company(turns[i]['text'])
            c2 = extract_company(turns[i+1]['text'])
            if c1 and c2 and c1 == c2:
                violations.append({
                    'rule_id': 'R11',
                    'rule_name': '公司自我介绍冗余重复',
                    'severity': '中',
                    'evidence': 'AI连续两轮提及同一公司: ' + turns[i]['text'][:60] + ' | ' + turns[i+1]['text'][:60],
                    'suggestion': 'AI在相邻两个轮次中对同一家公司进行了两次介绍，应合并为一次。'
                })
                found_r11 = True

    # R12: 用户要在平台查看仍强推简历
    found_r12 = False
    for i, t in enumerate(turns):
        if found_r12:
            break
        if t['speaker'] == '用户':
            txt = t['text']
            if any(p in txt for p in ['平台上','猎聘上','APP上','平台上发','分享JD','在平台','app上','那个APP上']):
                for j in range(i+1, len(turns)):
                    if turns[j]['speaker'] == 'AI':
                        ai_resp = turns[j]['text']
                        if '简历' in ai_resp and 'HR' in ai_resp:
                            violations.append({
                                'rule_id': 'R12',
                                'rule_name': '用户要在平台查看仍强推简历',
                                'severity': '中',
                                'evidence': '用户: ' + txt + ' | AI: ' + ai_resp,
                                'suggestion': '用户明确表示想在平台查看岗位信息，AI应尊重用户自主选择权，而非仍推送将简历给HR。'
                            })
                            found_r12 = True
                        break

    # R13: 用户同意后重复要简历
    found_r13 = False
    user_agreed = False
    for i, t in enumerate(turns):
        if found_r13:
            break
        if t['speaker'] == '用户':
            txt = t['text']
            # Only count clear agreement, not "可以晚点" or "可以在APP上"
            clear_agree = any(p in txt for p in ['可以可以','可以呀','嗯，可以','好的好的','可以的','嗯，好的','好，行','嗯可以','可以啊'])
            # Exclude cases where user says "可以在APP上" or "可以晚点"
            if clear_agree and 'APP' not in txt and '猎聘' not in txt and '平台' not in txt:
                user_agreed = True
        if t['speaker'] == 'AI' and user_agreed:
            if '简历' in t['text'] and ('HR' in t['text'] or '企业' in t['text']):
                violations.append({
                    'rule_id': 'R13',
                    'rule_name': '用户同意后重复要简历',
                    'severity': '低',
                    'evidence': '用户已明确同意后 | AI: ' + t['text'][:80],
                    'suggestion': '用户已明确同意后，AI不应再次重复询问是否可以把简历给HR，应直接推进到后续安排。'
                })
                found_r13 = True

    results.append({'id': cid, 'violations': violations})

total_v = sum(len(r['violations']) for r in results)
convs_with_v = sum(1 for r in results if r['violations'])
print(f'Total conversations: {len(results)}')
print(f'Total violations found: {total_v}')
print(f'Conversations with violations: {convs_with_v}')
for r in results:
    if r['violations']:
        for v in r['violations']:
            print(f'  {r["id"]}: {v["rule_id"]} - {v["rule_name"]}')

# Save results
with open('C:/Users/dongyi/myprojects/auto-qc/tmp/results_v2.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
