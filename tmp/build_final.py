import re, json

with open('C:/Users/dongyi/myprojects/auto-qc/tmp/results_v2.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

# Load parsed convs for reference
with open('C:/Users/dongyi/myprojects/auto-qc/tmp/worker_prompts/batch_4.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

conversations = []
blocks = raw.split('=== ')
for block in blocks[1:]:
    lines = block.strip().split('\n')
    header = lines[0]
    conv_id = header.split('(')[0].strip().replace('对话', '').strip()
    turns = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('AI:'):
            turns.append({'speaker': 'AI', 'text': line[3:].strip()})
        elif line.startswith('用户:'):
            turns.append({'speaker': '用户', 'text': line[3:].strip()})
    conversations.append({'id': conv_id, 'turns': turns})

conv_map = {c['id']: c for c in conversations}

# Build final results list
final_results = []
for r in results:
    cid = r['id']
    vs = r['violations']
    # Deduplicate violations by rule_id (keep first)
    seen_rules = set()
    deduped = []
    for v in vs:
        if v['rule_id'] not in seen_rules:
            seen_rules.add(v['rule_id'])
            deduped.append(v)

    status = 'violation' if deduped else 'pass'
    final_results.append({
        'id': cid,
        'status': status,
        'violations': deduped
    })

# Now build spot_check_details with detailed reasoning for 5 conversations
spot_checks = []

# Spot check 1: 11228776342 - R05 violation
conv = conv_map['11228776342']
reasoning1 = "逐条检查所有13条规则：R01: 用户未明确拒绝，无触发。R02: AI最后一条发言包含'祝您生活愉快，再见'，正常结束。R03: AI各轮发言内容不同，无重复。R04: 公司名'恒华数字科技集团有限公司'不含城市标识，地点'北京朝阳区'，无矛盾。R05: 用户问'主要工作以设计为主是吗还是说以优化什么的为主'，这是对岗位具体工作内容的追问，AI未给出任何实质性回答，直接跳转到'呃好，那稍后我把您的简历还有联系方式呢给企业HR看一下'，完全回避了用户的问题，触发R05。R06: AI确认意向仅2次（要不要接触、您看可以吗），未达3次阈值。R07: 无连续无应答场景。R08: 用户未表示不便。R09: 无信号误判。R10: 结束语格式正常。R11: 无连续两轮同公司介绍。R12: 用户未要求在平台查看。R13: 用户说'行，可以可以可以'后AI没有重复要简历。最终判定：violation (R05)。"
spot_checks.append({'id': '11228776342', 'reasoning': reasoning1})

# Spot check 2: 11189265895 - R06, R08, R09
conv = conv_map['11189265895']
reasoning2 = "逐条检查所有13条规则：R01: 用户未明确拒绝。R02: AI最后发言'您这边信号不太好，我现在听不见您说话，那我回头再联系您吧，再见。'包含'再见'，正常结束。R03: 各轮AI发言不同，无重复。R04: 公司名'青岛众屹科锐工程技术有限公司'无城市标识，地点'青岛城阳区'，一致。R05: 用户无具体追问岗位/公司细节。R06: AI在对话中4次发出确认意向提问（'要不要接触一下'、'您看可以吗'、'你们详细沟通下怎么样'、'您看行吗'），超过2次阈值，触发R06。R07: 用户有发言，不属于无应答场景。R08: 用户说'一会儿，一会儿我去那边看一下，我现在在忙啊'表示在忙，AI没有约定下次联系时间，而是继续追问确认意向，触发R08。R09: AI说'您这边信号不太好，我现在听不见您说话'，但此前用户有明确发言'一会儿吧，一会儿吧我看完我看完再说吧，好吧'，属于误判信号，触发R09。R10: 结束语格式正常。R11: 无连续两轮同公司介绍。R12: 用户未要求在平台查看。R13: 用户未明确同意后重复要简历。最终判定：violation (R06, R08, R09)。"
spot_checks.append({'id': '11189265895', 'reasoning': reasoning2})

# Spot check 3: 11195799789 - R02, R03
conv = conv_map['11195799789']
reasoning3 = "逐条检查所有13条规则：R01: 用户未明确拒绝。R02: 用户有实质性发言（'哎哎，你好我是问你们...'、'嗯，大家认真办去了啊'、'我信号太不好了'），但AI最后一条发言是岗位介绍'呃，是这样的，这家企业是益技欧电子器件有限公司...'，没有包含任何告别关键词，通话突然中断，触发R02。R03: AI在两个不同轮次中完整重复播报了完全相同的岗位介绍'呃，是这样的，这家企业是益技欧电子器件有限公司。给到的岗位是,被动元件首席采购员,./这个工作地点在苏州太仓市嗯这边在猎聘上也给您发了职位信息,./您看呃就是要不要接触一下呢？'，触发R03。R04: 公司名无城市标识，地点'苏州太仓市'，无矛盾。R05-R09: 无触发。R10: 无结束话术乱码。R11: 虽然两轮同公司介绍，但中间隔了用户发言，不是相邻轮次。R12-R13: 无触发。最终判定：violation (R02, R03)。"
spot_checks.append({'id': '11195799789', 'reasoning': reasoning3})

# Spot check 4: 11115944326 - R06, R12, R13
conv = conv_map['11115944326']
reasoning4 = "逐条检查所有13条规则：R01: 用户未明确拒绝。R02: AI最后发言包含'祝您生活愉快，再见'，正常结束。R03: 各轮AI发言不同。R04: 公司名'力鼎智能装备集团有限公司'无城市标识，地点'青岛城阳区'，无矛盾。R05: 用户未追问具体岗位/公司细节。R06: AI在对话中4次发出确认意向提问（'要不要接触一下'、'有兴趣跟企业接触一下吗'、'您看这个机会是否还要接触一下呢'、'您看可以吗'），超过2次阈值，触发R06。R07: 无连续无应答。R08: 用户未表示不便。R09: 无信号误判。R10: 结束语格式正常。R11: 无相邻两轮同公司介绍。R12: 用户说'我先看一下你们那个在平台上发的信息我感觉合适的话，然后咱们再联系，嗯，我在直接在上面回复可以吧'，明确表示想在平台查看并直接在上面回复，AI回应'呃好，那稍后我把您的简历还有联系方式呢给企业HR看一下，如果合适的话企业HR会再联系您,您看可以吗？'仍推送将简历给HR，触发R12。R13: 用户说'可以可以'同意后，AI仍重复问'您看可以吗'要简历，触发R13。最终判定：violation (R06, R12, R13)。"
spot_checks.append({'id': '11115944326', 'reasoning': reasoning4})

# Spot check 5: 11191692883 - R03, R06
conv = conv_map['11191692883']
reasoning5 = "逐条检查所有13条规则：R01: 用户未明确拒绝。R02: AI最后发言包含'祝您生活愉快，再见'，正常结束。R03: AI在两个轮次中完整重复播报了'呃您好，要么我先把您简历给企业HR看看，合适的话企业HR就直接联系您，您看行吗'，触发R03。R04: 公司名'上海大界机器人科技有限公司'无城市标识，地点'上海宝山区'，一致。R05: 用户追问'公司是多少人的公司啊'，AI回应'这个职位相关信息已经在猎聘上发送给您了哈'未正面回答公司规模，但后面还有实质性交互，且AI在轮次中确实提供了公司信息'嗯他们公司是叫上海大界机器人科技有限公司'，不算纯粹回避。暂不标记R05（ borderline case）。R06: AI在对话中至少7次重复确认意向（'要不要接触一下'、'愿意接触一下吗'、'您愿意接触一下吗'、'您看可以吗'、'您看行吗'出现多次、'详细沟通下怎么样'），远超2次阈值，触发R06。R07: 无连续无应答。R08: 用户说'稍等一下'但未标记为真正不便（属于等待查看）。R09: 无信号误判。R10: 结束语格式正常。R11: 无相邻两轮同公司介绍。R12: 用户未要求在平台查看。R13: 用户说'对'同意前AI已多次要简历，但不构成同意后再重复。最终判定：violation (R03, R06)。"
spot_checks.append({'id': '11191692883', 'reasoning': reasoning5})

# Build final output
output = {
    'batch_id': 4,
    'rules_checked': ['R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R08', 'R09', 'R10', 'R11', 'R12', 'R13'],
    'spot_check_details': spot_checks,
    'results': final_results
}

with open('C:/Users/dongyi/myprojects/auto-qc/tmp/batch_result_4.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Validate
print(f'batch_id: {output["batch_id"]}')
print(f'rules_checked: {len(output["rules_checked"])}')
print(f'spot_check_details: {len(output["spot_check_details"])}')
print(f'results: {len(output["results"])}')
v_count = sum(1 for r in output['results'] if r['status'] == 'violation')
p_count = sum(1 for r in output['results'] if r['status'] == 'pass')
print(f'violations: {v_count}, passes: {p_count}')
ids = [r['id'] for r in output['results']]
print(f'unique ids: {len(set(ids))}')
# Check all violations have required fields
for r in output['results']:
    assert 'id' in r and 'status' in r and 'violations' in r
    for v in r['violations']:
        assert 'rule_id' in v and 'rule_name' in v and 'severity' in v and 'evidence' in v and 'suggestion' in v
print('All validations passed!')
