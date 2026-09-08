from services.llm.server import extract_sentences


def test_short_opener_attaches_to_following_sentence():
    # When tokens stream with trailing space
    text = "Understood. How can I assist you today? "
    chunks, remainder = extract_sentences(text, min_words=4)
    # The complete sentence should be emitted together rather than split on 'Understood.'
    assert chunks == ["Understood. How can I assist you today?"]
    assert remainder.strip() == ""


def test_got_it_attaches():
    text = "Got it. What can I help you with today? "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["Got it. What can I help you with today?"]
    assert remainder.strip() == ""


def test_sure_attaches():
    text = "Sure. The foundation is open from 9:00 AM to 5:00 PM. "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["Sure. The foundation is open from 9:00 AM to 5:00 PM."]
    assert remainder.strip() == ""


def test_okay_attaches():
    text = "Okay. I will help you with that right now. "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["Okay. I will help you with that right now."]
    assert remainder.strip() == ""


def test_normal_sentences_still_split():
    text = "The main office is located in Balotra. It is open Monday through Saturday. "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["The main office is located in Balotra.", "It is open Monday through Saturday."]
    assert remainder.strip() == ""


def test_abbreviations_do_not_split():
    text = "Dr. Sanjay is available at the clinic. He will assist you today. "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["Dr. Sanjay is available at the clinic.", "He will assist you today."]
    assert remainder.strip() == ""


def test_time_and_currency_do_not_split():
    text = "Our office opens at 9:00 a.m. sharp. The donation amount is Rs. 5000 today. "
    chunks, remainder = extract_sentences(text, min_words=4)
    assert chunks == ["Our office opens at 9:00 a.m. sharp.", "The donation amount is Rs. 5000 today."]
    assert remainder.strip() == ""


if __name__ == "__main__":
    test_short_opener_attaches_to_following_sentence()
    test_got_it_attaches()
    test_sure_attaches()
    test_okay_attaches()
    test_normal_sentences_still_split()
    test_abbreviations_do_not_split()
    test_time_and_currency_do_not_split()
    print("All tokenizer unit tests passed successfully!")
