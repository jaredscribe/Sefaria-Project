# -*- coding: utf-8 -*-

"""
http://norvig.com/spell-correct.html
http://scottlobdell.me/2015/02/writing-autocomplete-engine-scratch-python/
"""
from collections import Counter, defaultdict
from sefaria.utils import hebrew
import logging
logger = logging.getLogger(__name__)

try:
    import re2 as re
    re.set_fallback_notification(re.FALLBACK_WARNING)
except ImportError:
    logging.warning("Failed to load 're2'.  Falling back to 're' for regular expression parsing. See https://github.com/blockspeiser/Sefaria-Project/wiki/Regular-Expression-Engines")
    import re


class SpellChecker(object):

    def __init__(self, lang, phrases=None):
        assert lang in ["en", "he"]
        self.lang = lang
        if lang == "en":
            self.letters = u'abcdefghijklmnopqrstuvwxyz'
        else:
            self.letters = hebrew.ALPHABET_22
        self.WORDS = defaultdict(int)
        if phrases:
            self.train_phrases(phrases)

    def words(self, text):
        if self.lang == "en":
            return re.findall(r'\w+', text.lower())
        return re.split(ur"\s+", text)

    def train_phrases(self, phrases):
        for p in phrases:
            if self.lang == "he":
                p = hebrew.normalize_final_letters_in_str(p)
            for w in self.words(p):
                self.WORDS[w] += 1

    def train_words(self, words):
        for w in words:
            if self.lang == "he":
                w = hebrew.normalize_final_letters_in_str(w)
            self.WORDS[w] += 1

    def _edits1(self, word):
        """All edits that are one edit away from `word`."""
        splits     = [(word[:i], word[i:])    for i in range(len(word) + 1)]
        deletes    = [L + R[1:]               for L, R in splits if R]
        transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R)>1]
        replaces   = [L + c + R[1:]           for L, R in splits if R for c in self.letters]
        inserts    = [L + c + R               for L, R in splits for c in self.letters]
        return set(deletes + transposes + replaces + inserts)

    def _known_edits2(self, word):
        """All edits that are two edits away from `word`."""
        return (e2 for e1 in self._edits1(word) for e2 in self._edits1(e1) if e2 in self.WORDS)

    def _known(self, words):
        """The subset of `words` that appear in the dictionary of WORDS."""
        return set(w for w in words if w in self.WORDS)

    """
    Do we need this, as well as correct_token?
    def candidates(self, word):
        return self._known([word]) or self._known(self._edits1(word)) or self._known_edits2(word) or [word]
    """

    def correct_token(self, token):
        candidates = self._known([token]) or self._known(self._edits1(token)) or self._known_edits2(token) or [token]
        return max(candidates, key=self.WORDS.get)

    def correct_phrase(self, text):
        if self.lang == "he":
            text = hebrew.normalize_final_letters_in_str(text)
        tokens = self.words(text)
        return [self.correct_token(token) for token in tokens]

    """
    def P(word, N=sum(WORDS.values())):
        "Probability of `word`."

    def correction(word):
        "Most probable spelling correction for word."
        return max(candidates(word), key=P)

    def candidates(word):
        "Generate possible spelling corrections for word."
        return (known([word]) or known(edits1(word)) or known(edits2(word)) or [word])

    """


class AutoCompleter(object):
    MIN_N_GRAM_SIZE = 3

    def __init__(self, lang, titles=None):
        assert lang in ["en", "he"]
        self.lang = lang
        self.token_to_title = defaultdict(list)
        self.n_gram_to_tokens = defaultdict(set)
        if titles:
            self._learn_titles(titles)

    def _learn_titles(self, titles):
        for title in titles:
            title = title.lower().replace(u"-", u" ").replace(u"(", u" ").replace(u")", u" ").replace(u"'", u" ")
            tokens = title.split()
            for token in tokens:
                self.token_to_title[token].append(title)
                for string_size in xrange(self.MIN_N_GRAM_SIZE, len(token) + 1):
                    n_gram = token[:string_size]
                    self.n_gram_to_tokens[n_gram].add(token)

    def _get_real_tokens_from_possible_n_grams(self, tokens):
        real_tokens = []
        for token in tokens:
            token_set = self.n_gram_to_tokens.get(token, set())
            real_tokens.extend(list(token_set))
        return real_tokens

    def _get_scored_titles_uncollapsed(self, real_tokens):
        exercises__scores = []
        for token in real_tokens:
            possible_exercises = self.token_to_title.get(token, [])
            for exercise_name in possible_exercises:
                score = float(len(token)) / len(exercise_name.replace(" ", ""))
                exercises__scores.append((exercise_name, score))
        return exercises__scores

    def _combined_title_scores(self, titles__scores, num_tokens):
        collapsed_title_to_score = defaultdict(int)
        collapsed_title_to_occurence = defaultdict(int)
        for title, score in titles__scores:
            collapsed_title_to_score[title] += score
            collapsed_title_to_occurence[title] += 1
        for title in collapsed_title_to_score.keys():
            collapsed_title_to_score[title] *= collapsed_title_to_occurence[title] / float(num_tokens)
        return collapsed_title_to_score

    def _filtered_results(self, titles__scores):
        min_results = 3
        max_results = 10
        score_threshold = 0.4
        max_possibles = titles__scores[:max_results]
        if titles__scores and titles__scores[0][1] == 1.0:
            return [titles__scores[0][0]]

        possibles_within_thresh = [tuple_obj for tuple_obj in titles__scores if tuple_obj[1] >= score_threshold]
        min_possibles = possibles_within_thresh if len(possibles_within_thresh) > min_results else max_possibles[:min_results]
        return [tuple_obj[0] for tuple_obj in min_possibles]

    def guess_titles(self, tokens):
        real_tokens = self._get_real_tokens_from_possible_n_grams(tokens)
        titles__scores = self._get_scored_titles_uncollapsed(real_tokens)
        collapsed_titles_to_score = self._combined_title_scores(titles__scores, len(tokens))
        titles__scores = collapsed_titles_to_score.items()
        titles__scores.sort(key=lambda t: t[1], reverse=True)
        return self._filtered_results(titles__scores)
