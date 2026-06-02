import json

# Read the conversations from the prompt file
with open(r"C:/Users/dongyi/.claude/skills/auto-qc/tmp/batches/batch_1_prompt.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Extract JSON array of conversations
start = content.index("[\n  {\n    \"id\":")
# Find the matching closing bracket
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

conv_json = content[start:end]
conversations = json.loads(conv_json)
print(f"Loaded {len(conversations)} conversations")

# Parse rules
rules_start = content.index('{\n  "rules":')
rules_end = content.index("}\n\n##") + 1
rules_json = content[rules_start:rules_end]
rules_data = json.loads(rules_json)
rules = rules_data["rules"]

print(f"Loaded {len(rules)} rules")
for r in rules:
    print(f"  {r['rule_id']}: {r['name']}")

