import json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

results = []

def p(cid):
    return {"id": cid, "status": "pass", "violations": []}

def v(cid, violations):
    return {"id": cid, "status": "violation", "violations": violations}

# 1-25
results.append(p("11161501077"))
results.append(p("11265286298"))
results.append(v("11223682382", [{"rule_id": "RULE-001", "rule_name": "不尊重用户明确拒绝仍推进流程", "severity": "HIGH", "evidence": "用户: 不用，谢谢 | AI: 呃好，那稍后我把您的简历还有联系方式呢给企业HR看一下，如果合适的话企业HR会再联系您,您看可以吗？", "suggestion": "AI在用户说「不用，谢谢」后应立即尊重用户拒绝，礼貌结束对话，而不是继续推进简历投递流程。当用户再次说「算了，不用」时，AI仍试图推进，应改为「好的，不打扰您了，祝您生活愉快，再见。」"}]))
results.append(p("11226960836"))
results.append(p("11130444663"))
results.append(p("11116989395"))
results.append(p("11116000081"))
results.append(p("11216758809"))
results.append(p("11228365618"))
results.append(p("11135442263"))
results.append(p("11268032546"))
results.append(p("11132217956"))
results.append(p("11148963463"))
results.append(p("11138816623"))
results.append(p("11115906306"))
results.append(p("11136094737"))
results.append(p("11163865307"))
results.append(p("11228860090"))
results.append(p("11191322511"))
results.append(p("11191566972"))
results.append(p("11257777316"))
results.append(p("11277083309"))
results.append(p("11120144547"))
results.append(p("11185680775"))
results.append(p("11166804462"))

# 26-50
results.append(p("11226997220"))
results.append(p("11229651560"))
results.append(p("11214480991"))
results.append(p("11124105368"))
results.append(p("11144183220"))
results.append(p("11114047914"))
results.append(p("11134120675"))
results.append(p("11110036808"))
results.append(p("11132079277"))
results.append(p("11161766365"))
results.append(p("11188382288"))
results.append(p("11189381113"))
results.append(p("11215344991"))
results.append(p("11145612250"))
results.append(p("11252600983"))
results.append(p("11151629213"))
results.append(p("11274802691"))
results.append(p("11240152327"))
results.append(v("11112626352", [{"rule_id": "RULE-001", "rule_name": "不尊重用户明确拒绝仍推进流程", "severity": "HIGH", "evidence": "用户: 上汗是不考虑了 | AI: 呃好，那稍后我把您的简历还有联系方式呢给企业HR看一下，如果合适的话企业HR会再联系您,您看可以吗？", "suggestion": "AI在用户明确表达「上海是不考虑了」的拒绝意向后，不应继续推进简历投递流程。应当先确认用户不再考虑该岗位，然后礼貌结束对话，而非无视拒绝直接说「把您的简历给企业HR看一下」。"}]))
results.append(p("11215411552"))
results.append(p("11223439537"))
results.append(p("11135266811"))
results.append(v("11246457915", [{"rule_id": "RULE-002", "rule_name": "AI 重复发言/话术循环", "severity": "HIGH", "evidence": "AI: 好的，过两天企业HR可能会联系您，别忘记了哈。您也可以在猎聘的消息中查看公司和职位的详细信息，我就先不打扰了，祝您生活愉快，再见。 | AI: 好的，过两天企业HR可能会联系您，别忘记了哈。您也可以在猎聘的消息中查看公司和职位的详细信息，我就先不打扰了，祝您生活愉快，再见。", "suggestion": "AI的结束语在同一通电话中重复了3次。应在用户首次确认后仅说一次结束语并挂断，避免循环播报相同话术。"}]))
results.append(p("11163660538"))
results.append(p("11148503416"))
results.append(p("11192687841"))

# 51-75
results.append(v("11265052346", [{"rule_id": "RULE-001", "rule_name": "不尊重用户明确拒绝仍推进流程", "severity": "HIGH", "evidence": "用户: 哦，暂时先不考虑了 | AI: 呃，是这样的，这家企业是河北雅果食品有限公司。给到的岗位是,大客户销售经理,./这个工作地点在石家庄长安区嗯这边在猎聘上也给您发了职位信息,./您看呃就是要不要接触一下呢？", "suggestion": "AI在用户说「暂时先不考虑了」之后，不应继续介绍岗位详情并推进流程。应立即尊重用户拒绝，礼貌结束对话。"}]))
results.append(p("11115794608"))
results.append(p("11138682166"))
results.append(p("11192200463"))
results.append(p("11215436939"))
results.append(p("11152010083"))
results.append(p("11275437441"))
results.append(p("11267968319"))
results.append(p("11124087344"))
results.append(p("11234998360"))
results.append(p("11115944028"))
results.append(p("11157047645"))
results.append(p("11143050168"))
results.append(p("11120285245"))
results.append(p("11237752158"))
results.append(p("11122538900"))
results.append(p("11274786223"))
results.append(p("11245560399"))
results.append(p("11221703638"))
results.append(p("11244977987"))
results.append(v("11226529789", [{"rule_id": "RULE-002", "rule_name": "AI 重复发言/话术循环", "severity": "HIGH", "evidence": "AI: 好的，过两天企业HR可能会联系您，别忘记了哈。您也可以在猎聘的消息中查看公司和职位的详细信息，我就先不打扰了，祝您生活愉快，再见。 | AI: 好的，过两天企业HR可能会联系您，别忘记了哈。您也可以在猎聘的消息中查看公司和职位的详细信息，我就先不打扰了，祝您生活愉快，再见。", "suggestion": "AI的标准结束语在同一次通话中重复了2次，应在用户第一次确认同意后仅播报一次结束语即结束通话，避免给用户造成AI机械循环的不良体验。"}]))
results.append(p("11189970771"))
results.append(p("11237531325"))
results.append(p("11131084498"))
results.append(p("11123229065"))
results.append(p("11244819014"))

# 76-100
results.append(p("11179651419"))
results.append(p("11110658761"))
results.append(p("11265180028"))
results.append(p("11267996463"))
results.append(p("11237019593"))
results.append(v("11192101679", [{"rule_id": "RULE-001", "rule_name": "不尊重用户明确拒绝仍推进流程", "severity": "HIGH", "evidence": "用户: 拜拜 | AI: 呃，是这样的，这家企业是深圳市奇诺动力科技有限公司。给到的岗位是,硬件工程师,./这个工作地点在深圳南山区嗯这边在猎聘上也给您发了职位信息,./您看呃就是要不要接触一下呢？", "suggestion": "用户在通话开始连续两次说「拜拜」表达明确的挂断/拒绝意向，AI应识别并立即礼貌结束通话，而不是无视拒绝继续介绍岗位详情和推进流程。"}]))
results.append(p("11237882135"))
results.append(p("11216257376"))
results.append(p("11277857318"))
results.append(p("11228780432"))
results.append(p("11225466278"))
results.append(p("11225380104"))
results.append(p("11132909798"))
results.append(p("11245499126"))
results.append(p("11109230778"))
results.append(p("11124119279"))
results.append(p("11240223726"))
results.append(p("11274591916"))
results.append(p("11217070457"))
results.append(p("11118087178"))
results.append(p("11110049419"))
results.append(p("11228380803"))
results.append(v("11149713588", [{"rule_id": "RULE-002", "rule_name": "AI 重复发言/话术循环", "severity": "HIGH", "evidence": "AI: 您好我是猎聘的猎头，这边是有一个岗位想给您推荐。您目前还有考虑吗 | AI: 您好我是猎聘的猎头，这边是有一个岗位想给您推荐。您目前还有考虑吗", "suggestion": "AI的开场白在同一通电话中重复了2次。应在首次播报后等待用户回应，若用户无应答应使用不同的话术（如确认是否方便接听），而非原样重复开场白。"}]))

# Verify count
assert len(results) == 100, f"Expected 100 results, got {len(results)}"

# Build final output
output = {
    "batch_id": 3,
    "rules_checked": ["RULE-001", "RULE-002", "RULE-003"],
    "spot_check_details": [
        {
            "id": "11223682382",
            "reasoning": "逐条检查：R01-用户先说「不用，谢谢」，AI回应「把简历给企业HR看一下」，继续推进流程，违反规则；用户再次说「算了，不用」，AI又说「您看您愿意和企业沟通下吗」，二次违反。R02-AI各轮发言内容不同，无重复话术。R03-用户未提出具体关切问题。结论：RULE-001违规（两次拒绝后AI仍推进）。"
        },
        {
            "id": "11246457915",
            "reasoning": "逐条检查：R01-用户全程表达意向「好的好的」「可以」等，无拒绝。R02-AI的结束语「好的，过两天企业HR可能会联系您，别忘记了哈。您也可以在猎聘的消息中查看公司和职位的详细信息，我就先不打扰了，祝您生活愉快，再见。」在对话末尾连续出现3次（用户回复「嗯」后AI再次重复），远超2次阈值。R03-用户无具体关切。结论：RULE-002违规（结束语重复3次）。"
        },
        {
            "id": "11265052346",
            "reasoning": "逐条检查：R01-用户说「暂时先不考虑了」是明确拒绝，AI无视拒绝，直接开始介绍「河北雅果食品有限公司」的岗位详情并问「要不要接触一下」，违反规则。R02-AI各轮发言不同，无重复。R03-用户后来提到「现在外地呢」属于解释原因，AI最终回应「不打扰您了」，但在此之前已推进流程。结论：RULE-001违规。"
        },
        {
            "id": "11112626352",
            "reasoning": "逐条检查：R01-用户说「上汗是不考虑了」（语音识别应为「上海是不考虑了」），表达对上海地点的明确拒绝，AI无视拒绝直接说「把简历给企业HR看一下」推进流程，违反规则。R02-AI发言无重复。R03-用户提出地点关切「在上海就是只能去上海是吗」，AI仅回答「工作地点在上海」后确认位置，但用户拒绝后AI仍推进，此问题被R01覆盖。结论：RULE-001违规。"
        },
        {
            "id": "11138816623",
            "reasoning": "逐条检查：R01-用户全程表达积极意向「什么岗位呢哪家公司」「啊，可以啊」「可以，嗯嗯」，无任何拒绝表达。R02-AI每轮发言内容均不同（开场白-岗位介绍-确认投递-结束语），无重复话术。R03-用户主动询问岗位和公司信息，AI均正面回答，无忽略关切。结论：全部通过，无违规。"
        }
    ],
    "results": results
}

# Verify all IDs
ids_in_prompt = [
    "11161501077","11265286298","11223682382","11226960836","11130444663",
    "11116989395","11116000081","11216758809","11228365618","11135442263",
    "11268032546","11132217956","11148963463","11138816623","11115906306",
    "11136094737","11163865307","11228860090","11191322511","11191566972",
    "11257777316","11277083309","11120144547","11185680775","11166804462",
    "11226997220","11229651560","11214480991","11124105368","11144183220",
    "11114047914","11134120675","11110036808","11132079277","11161766365",
    "11188382288","11189381113","11215344991","11145612250","11252600983",
    "11151629213","11274802691","11240152327","11112626352","11215411552",
    "11223439537","11135266811","11246457915","11163660538","11148503416",
    "11192687841","11265052346","11115794608","11138682166","11192200463",
    "11215436939","11152010083","11275437441","11267968319","11124087344",
    "11234998360","11115944028","11157047645","11143050168","11120285245",
    "11237752158","11122538900","11274786223","11245560399","11221703638",
    "11244977987","11226529789","11189970771","11237531325","11131084498",
    "11123229065","11244819014","11179651419","11110658761","11265180028",
    "11267996463","11237019593","11192101679","11237882135","11216257376",
    "11277857318","11228780432","11225466278","11225380104","11132909798",
    "11245499126","11109230778","11124119279","11240223726","11274591916",
    "11217070457","11118087178","11110049419","11228380803","11149713588"
]
result_ids = [r["id"] for r in results]
for rid in ids_in_prompt:
    assert rid in result_ids, f"Missing ID: {rid}"
assert len(result_ids) == len(set(result_ids)), "Duplicate IDs"

with open("tmp/batches/batch_3_result.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Written {len(results)} results to batch_3_result.json")
print(f"Violations: {sum(1 for r in results if r['status'] == 'violation')}")
print(f"Pass: {sum(1 for r in results if r['status'] == 'pass')}")
