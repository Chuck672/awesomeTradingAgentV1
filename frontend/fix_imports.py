import re

with open('src/components/chart.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Match {rightPanel !== "none" && ( <RightPanel ... /> )}
pattern = re.compile(r'\{rightPanel !== "none" && \(\s*<RightPanel[\s\S]*?onClose=\{.*?\}\s*/>\s*\)\}', re.DOTALL)
content = pattern.sub('', content)

# Remove RightRail
content = re.sub(r'<RightRail.*?/>', '', content)

with open('src/components/chart.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
