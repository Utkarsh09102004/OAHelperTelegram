import json


def extract_question_from_text(json_string):
    try:
        # Strip the string so that it starts with '{' and ends with '}'
        start_index = json_string.find('{')
        end_index = json_string.rfind('}') + 1

        # If no valid JSON boundaries are found, return None
        if start_index == -1 or end_index == -1:
            return None

        # Extract the portion of the string that starts with '{' and ends with '}'
        json_string = json_string[start_index:end_index]

        # Apply necessary replacements
        cleaned_string = (json_string
                          .replace('\n', '\\n')  # Escape newlines
                          .replace('\\n"', '"')  # Fix comma-newline before string ending
                          .replace('"\\n}', '"}')  # Fix newline before JSON end bracket
                          )

        # Load the cleaned string into a Python object
        json_object = json.loads(cleaned_string)

        # Convert the JSON object back into a pretty-formatted JSON string


        return json_object

    except (json.JSONDecodeError, TypeError) as e:
        # Return None in case of any error
        return None


# Example usage:
json_string = '''```json
{
"1": "Construct the given grammar G:\nS → W\nW → ZXY | XY\nX → c | ε\nY → a | d\nZ → xb | ε\na) Compute First and Follow of all non-terminals for the given grammar G.\nb) Check whether given grammar is LL(1) or not by constructing the LL(1) parsing table.",
"2": "Given the regular expression *r = (aa | bb)*\na) Convert the given *r* into NFA using Thompson’s construction.\nb) Convert the obtained NFA into DFA using subset construction.\nc) Minimize the obtained DFA in 3(b).",
"3": "Consider the given grammar G:\nL → A l T\nA → n | id\nT → (M)\nM → ML | ε\nConsider n represent the number, a and x represents the identifier.\nFor the given input string (a 23) x\na) Write leftmost and rightmost derivation.\nb) Draw a parse tree for the given string."
}
```'''

# Test the function
result = extract_question_from_text(json_string)
print(result)
