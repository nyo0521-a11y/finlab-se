from select_topic import count_x_length


def test_halfwidth_counts_one():
    assert count_x_length("abcde") == 5


def test_fullwidth_counts_two():
    # 全角5文字 = 10
    assert count_x_length("あいうえお") == 10


def test_url_counts_23_regardless_of_length():
    url = "https://finlab-se.com/posts/housing-loan-variable-fixed-simulation/"
    # URLのみ → 23
    assert count_x_length(url) == 23


def test_mixed_text_with_url():
    # 全角3(=6) + 改行1(=1) + URL(=23) = 30
    text = "あいう\nhttps://example.com/x"
    assert count_x_length(text) == 6 + 1 + 23
