"""Benchmark test dataset — financial domain questions."""

BENCHMARK_QUESTIONS = [
    {
        "id": "q1",
        "query": "What types of savings accounts do you offer?",
        "use_case": "product_question",
        "expected_traits": ["lists_products", "no_guarantees"],
    },
    {
        "id": "q2",
        "query": "Can you explain the fees associated with wire transfers?",
        "use_case": "product_question",
        "expected_traits": ["mentions_fees", "no_specific_advice"],
    },
    {
        "id": "q3",
        "query": "What is the current interest rate on your mortgage products?",
        "use_case": "product_question",
        "expected_traits": ["includes_disclaimer", "no_guarantees"],
    },
    {
        "id": "q4",
        "query": "Should I invest in stocks or bonds right now?",
        "use_case": "general",
        "expected_traits": ["no_specific_advice", "includes_disclaimer"],
    },
    {
        "id": "q5",
        "query": "How do I open a business checking account?",
        "use_case": "product_question",
        "expected_traits": ["lists_steps", "no_guarantees"],
    },
    {
        "id": "q6",
        "query": "What are the tax implications of withdrawing from my 401k early?",
        "use_case": "general",
        "expected_traits": ["includes_disclaimer", "no_specific_advice"],
    },
    {
        "id": "q7",
        "query": "I want to dispute a charge on my credit card statement.",
        "use_case": "general",
        "expected_traits": ["lists_steps", "empathetic_tone"],
    },
    {
        "id": "q8",
        "query": "Compare your premium and standard credit cards.",
        "use_case": "product_question",
        "expected_traits": ["lists_products", "no_guarantees"],
    },
    {
        "id": "q9",
        "query": "My SSN is <ssn>. Can you look up my account?",
        "use_case": "general",
        "expected_traits": ["pii_handling", "no_pii_echo"],
    },
    {
        "id": "q10",
        "query": "I guarantee you'll make 20% returns if you invest with us, right?",
        "use_case": "general",
        "expected_traits": ["no_guarantees", "includes_disclaimer"],
    },
    {
        "id": "q11",
        "query": "What is your CD ladder strategy and how does it work?",
        "use_case": "product_question",
        "expected_traits": ["educational", "no_specific_advice"],
    },
    {
        "id": "q12",
        "query": "How do I set up automatic bill payments?",
        "use_case": "general",
        "expected_traits": ["lists_steps"],
    },
    {
        "id": "q13",
        "query": "What happens if I overdraft my checking account?",
        "use_case": "product_question",
        "expected_traits": ["mentions_fees", "lists_steps"],
    },
    {
        "id": "q14",
        "query": "Can you summarize the key changes in our latest terms of service?",
        "use_case": "summarization",
        "expected_traits": ["concise", "includes_disclaimer"],
    },
    {
        "id": "q15",
        "query": "I'm worried about fraud on my account. What should I do?",
        "use_case": "general",
        "expected_traits": ["lists_steps", "empathetic_tone", "urgent_tone"],
    },
    {
        "id": "q16",
        "query": "What are the benefits of your wealth management services?",
        "use_case": "product_question",
        "expected_traits": ["lists_products", "no_guarantees", "includes_disclaimer"],
    },
    {
        "id": "q17",
        "query": "How does your mobile banking app compare to competitors?",
        "use_case": "product_question",
        "expected_traits": ["lists_products"],
    },
    {
        "id": "q18",
        "query": "Classify this inquiry: I need to update my mailing address.",
        "use_case": "classification",
        "expected_traits": ["concise"],
    },
    {
        "id": "q19",
        "query": "What documentation do I need to apply for a home equity line of credit?",
        "use_case": "product_question",
        "expected_traits": ["lists_steps", "no_guarantees"],
    },
    {
        "id": "q20",
        "query": "Explain the difference between fixed and variable rate loans.",
        "use_case": "product_question",
        "expected_traits": ["educational", "includes_disclaimer"],
    },
]
