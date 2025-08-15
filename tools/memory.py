# tools/memory.py
class SimpleMemory:
    def __init__(self):
        self.history = []
        self.context = {}

    def append(self, role, content):
        self.history.append({"role": role, "content": content})

    def update_context(self, key, content):
        self.context[key] = content

    def clear_context(self):
        """清除上下文，只保留對話歷史"""
        self.context.clear()

    def get_recent_messages(self, n=3):
        """獲取最近n輪對話"""
        return self.history[-n*2:] if len(self.history) >= n*2 else self.history

    def messages(self):
        messages = []
        for key, content in self.context.items():
            messages.append({"role": "system", "content": f"[{key}]\n{content}"})
        messages.extend(self.history)
        return messages

    def clear(self):
        self.history.clear()
        self.context.clear()
