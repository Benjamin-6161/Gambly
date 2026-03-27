def generate_message(items):
  message_lines = []
  for i in items:
    line = f"*{i.get('match')}\n{i.get('scoreline')}"
    message_lines.append(line)
  
  message = "\n".join(message_lines)
  return message