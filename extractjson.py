import json

input = '''
{
"1": "Construct the given grammar G:\nS -> W\nW -> ZXY | XY\nY -> c | lambda\nZ -> Xb | d\nX -> Xb | e\na) Compute First and Follow of all non-terminals for the given grammar G.\nb) Check whether given grammar is LL(1) or not by constructing the LL(1) parsing table.",
"2": "Given the regular expression *r = (aa | bb)*\na) Convert the given *r into NFA using Thompson’s construction.\nb) Convert the obtained NFA into DFA using subset construction.\nc) Minimize the obtained DFA in 3(b).",
"3": "Consider the given grammar G:\nL -> A l T\nA -> n | lambda\nT -> (M) | l\nM -> ML | l\nConsider given input string (a 23, x) and x represents the identifier.\nFor the given input string (a 23, x):\na) Write leftmost and rightmost derivation.\nb) Draw a parse tree for the rightmost derivation."
}
'''
print(json.loads(input))