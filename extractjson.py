def extract_json(text):
    start = text.find('{')
    if start == -1:
        return None  # No JSON found

    in_string = False
    escape = False
    nesting = 0

    for i in range(start, len(text)):
        c = text[i]

        if c == '\\' and not escape:
            escape = True
            continue
        elif c == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if c == '{':
                nesting += 1
            elif c == '}':
                nesting -= 1
                if nesting == 0:
                    # Extract the JSON portion
                    json_text = text[start:i+1]
                    return json_text

        escape = False

    return None  # No matching '}' found

# Example usage:
text = '''this are the questions extracted in a json format, here you go

1:"hello",
2:"bye",

I hope you like the answer'''

json_content = extract_json(text)
print(json_content)
