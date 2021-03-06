#!/usr/bin/env python
from __future__ import division
"""MODULE_DESCRIPTION"""

__author__ = "Nick Sweet"
__copyright__ = "Copyright 2015, Cohrint"
__credits__ = ["Nick Sweet", "Nisar Ahmed"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Nick Sweet"
__email__ = "nick.sweet@colorado.edu"
__status__ = "Development"

import logging
from itertools import chain
from collections import OrderedDict

import numpy as np
import spacy.en

from cops_and_robots.human_tools.statement_template import StatementTemplate, get_all_statements

class Matcher(object):
    """short description of Matcher

    Parameters
    ----------
    filled_templates : tuple, optional
        Tuples generated by the `TDC_collection` class. First element is a
        string for the template type, the second element is an ordered dict
        of label/token pairs.
    """

    def __init__(self, nlp=None):
        if nlp is None:
            logging.info("Loading SpaCy...")
            self.nlp = spacy.en.English(parser=False, tagger=False)
            logging.info("Done!")
        else:
            self.nlp = nlp

        self.statement_template = StatementTemplate(add_actions=True,
                                                    add_more_relations=True,
                                                    add_more_targets=True,
                                                    add_certainties=True,
                                                    )

        self.template_slots = [['certainty'],
                               ['target'],
                               ['positivity'],
                               ['action','spatial_relation:object','spatial_relation:area'],
                               ['modifier','spatial_relation:movement','grounding:object','grounding:area'],
                               ['grounding:object','grounding:area'],
                              ]
        self.template_parents = {'certainty': [''],
                                 'target': ['certainty'],
                                 'positivity': ['target'],
                                 'action': ['positivity'],
                                 'modifier': ['action'],
                                 'spatial_relation:object': ['positivity'],
                                 'spatial_relation:area': ['positivity'],
                                 'spatial_relation:movement': ['action'],
                                 'grounding:object': ['spatial_relation:movement', 'spatial_relation:object'],
                                 'grounding:area': ['spatial_relation:movement', 'spatial_relation:object']
                                 }

        # from cops_and_robots.human_tools.human import generate_human_language_template
        # self.templates = generate_human_language_template()._asdict()
        # self._flatten_templates()
        # self._create_phrase_templates()

    def find_nearest_statements(self, filled_templates):
        self.filled_templates = filled_templates
        statements = []
        for ft in self.filled_templates:
            statement_type = ft[0].strip('1234567890')
            kwargs = {}
            for label, token in ft[1].iteritems():
                comparables = self.find_comparables(label)
                sorted_comparables = self.rate_comparables(token, comparables)

                label = label.split(':')[0]
                # Use most likely statement class
                kwargs[label] = sorted_comparables[0][0]
            statement = StatementTemplate.statement_classes[statement_type](**kwargs)
            statements.append(statement)
        return statements

    def find_comparables(self, label, merge_groups=True):
        """Finds a list of comparable terms to the label.

        The merge_groups parameter determines whether groups such as,
        "grounding:object" and "grounding:area" are merged together into
        a "grounding" group.
        """
        components = label.split(':')
        comparables = self.statement_template.components

        if merge_groups:
            comparables = comparables[components[0]]
            if isinstance(comparables, dict):
                comparables = [v for values in comparables.values() for v in values]
        else:
            for component in components:
                try:
                    comparables = comparables[component]
                except KeyError:
                    continue

        return comparables

    def rate_comparables(self, token, comparables):
        """Find normalized distance between token and all comparables.
        """
        n = len(comparables)
        if token == '':
            similarities = [1] * n

        else:
            similarities = []
            for comparable in comparables:
                comparable = self.nlp(unicode(comparable))
                tok = self.nlp(unicode(token.replace('_',' ')))
                s = tok.similarity(comparable)
                similarities.append(s)
        similarities = np.array(similarities, dtype=float)
        similarities /= similarities.sum()

        sorted_comparables = [(c,s) for (s,c) in
            sorted(zip(similarities, comparables), reverse=True)]

        return sorted_comparables


    def get_slotted_templates(self):
        """Fit templates into ordered 'slots' for comparison.
        """
        self.slotted_templates = []

        # Expand components into slotted template structure
        for labels in self.template_slots:
            components = {}
            for label in labels:
                label_parts = label.split(':')
                i = 0
                comps = self.statement_template.components
                while isinstance(comps, dict):
                    comps = comps[label_parts[i]]
                    i += 1
                components[label] = comps
            self.slotted_templates.append(components)


        # for i, slot in enumerate(slotted_templates):
        #     print "Level {} slots:".format(i)
        #     print slot

    def compare_statement_and_utterance(self, statement, labeled_utterance):

        utterance_keys = labeled_utterance.keys()
        slot_i = 0
        # r = 'I '
        prev_label = ''
        probability = 1
        for slot_level in self.template_slots:

            # Get component from the statement
            statement_token = ''
            for slot_label in slot_level:
                label = slot_label.split(':')[0]

                add_component = (prev_label in self.template_parents[slot_label] and
                                 hasattr(statement, label) and
                                 len(getattr(statement, label)) > 1)

                if add_component:
                    statement_token = getattr(statement, label)
                    prev_label = slot_label
                    break

            # Get component from the utterance
            try:
                utterance_token = labeled_utterance[slot_label]
            except KeyError:
                # print "NO utterance found for {}".format(slot_label)
                utterance_token = ''

            # Define uninformative transition probability
            # P(d_i | d_{i-1})
            
            if utterance_token == '' and statement_token == '':
                continue
            elif utterance_token == '':
                trans_prob = 0
            else:
                comparables = self.slotted_templates[slot_i][slot_label]
                trans_prob = 1 / len(comparables)


            # Define probability of utterance tok given utterance tok
            obs_prob = self.compare_tokens(statement_token, utterance_token, comparables) # P(t_i | d_i)

            # Custom rules
            obs_prob = self.apply_custom_token_rules(statement_token, utterance_token, obs_prob)

            # print utterance_token, statement_token
            # print obs_prob, trans_prob

            slot_i += 1
            probability *= obs_prob * trans_prob
        # print statement, probability
        return probability

    def apply_custom_token_rules(self, statement_token, utterance_token, obs_prob):
        # Negations
        if statement_token == 'is' and ("n't" in utterance_token or
                                        "not" in utterance_token.split(' ')):
            obs_prob = 0

        if statement_token == 'is not' and ("n't" not in utterance_token and
                                            "not" not in utterance_token.split(' ')):
            obs_prob = 0

        # Proper names
        if 'Zhora' in statement_token and 'Zhora' in utterance_token:
            obs_prob = 1
        if 'Pris' in statement_token and 'Pris' in utterance_token:
            obs_prob = 1
        if 'Roy' in statement_token and 'Roy' in utterance_token:
            obs_prob = 1
        if 'Deckard' in statement_token and 'Deckard' in utterance_token:
            obs_prob = 1

        return obs_prob


    def compare_tokens(self, statement_token, utterance_token, comparables):
        if '' in [statement_token, utterance_token]:
            return 0

        statement_token = self.nlp(unicode(statement_token.replace('_',' ')))
        utterance_token = self.nlp(unicode(utterance_token.replace('_',' ')))
        s_true = statement_token.similarity(utterance_token)
        s_true *= statement_token.vector_norm
        s_true *= utterance_token.vector_norm

        s = s_true
        # print s, statement_token, utterance_token
        # M = 0
        # for comparable in comparables:
        #     comparable_token = self.nlp(unicode(comparable.replace('_',' ')))
        #     m = comparable_token.similarity(utterance_token)
        #     m *= comparable_token.vector_norm
        #     m *= utterance_token.vector_norm
        #     M += m
        # s = np.exp(s_true) / np.exp(M)
        # print s

        return s


    def compare_slots(self, labeled_utterance, show_n=None):
        self.get_slotted_templates()
        statements = get_all_statements(flatten=True,
                                        add_actions=True,
                                        add_more_relations=True,
                                        add_more_targets=True,
                                        add_certainties=True,
                                        )
        probabilities = []
        for statement in statements:
            prob = self.compare_statement_and_utterance(statement, labeled_utterance)
            probabilities.append(prob)
        probabilities = np.array(probabilities)
        probabilities /= probabilities.sum()


        str_ = "I"
        for _, token in labeled_utterance.iteritems():
            str_ += " " + token
        str_ += "."
        logging.info("Input phrase: {}".format(str_))


        s = []
        for i, probability in enumerate(probabilities):
            s.append((probability, statements[i]))

        s = sorted(s, reverse=True)
        logging.info(len(s))
        if show_n is not None:
            s = s[:show_n]

        for t in s:
            logging.info("{} ({:0.4f})".format(t[1], t[0]))

        logging.info('\n')
        return s[0][1]

            # self.get_slotted_utterance_components(filled_template)

    # def _flatten_templates(self):
    #     flat_templates = {}
    #     for key, value in self.templates.iteritems():
    #         if isinstance(value, dict):
    #             value = list(chain(*value.values()))

    #         #<>TODO: match keys to *unified* variable names
    #         if key == 'target_names':
    #             key = 'target'
    #         if key == 'positivities':
    #             key = 'positivity'
    #         if key == 'certainties':
    #             key = 'certainty'
    #         if key == 'relations':
    #             key = 'spatialrelation'
    #         if key == 'actions':
    #             key = 'action'
    #         if key == 'modifiers':
    #             key = 'modifier'
    #         if key == 'groundings':
    #             key = 'grounding'

    #         flat_templates[key.upper()] = value
    #     self.templates = flat_templates

    # def _create_phrase_templates(self):
    #     self.phrase_templates = {}
    #     d = OrderedDict([('I', 'I'),
    #                      ('CERTAINTY', 'know'),
    #                      ('TARGET', ''),
    #                      ('POSITIVITY', ''),
    #                      ('SPATIALRELATION', ''),
    #                      ('GROUNDING', ''),
    #                      ('.', '.'),
    #                      ])
    #     self.phrase_templates['spatial relation'] = d
    #     d = OrderedDict([('I', 'I'),
    #                      ('CERTAINTY', 'know'),
    #                      ('TARGET', ''),
    #                      ('POSITIVITY', ''),
    #                      ('ACTION', ''),
    #                      ('MODIFIER', ''),
    #                      ('GROUNDING', ''),
    #                      ('.', '.'),
    #                      ])
    #     self.phrase_templates['action'] = d

    # def find_closest_phrases(self, TDC_collection):
    #     closest = []
    #     for i, TDC in enumerate(TDC_collection.TDCs):
    #         tagged_phrase = TDC.to_tagged_phrase()
    #         p, t = self.find_closest_phrase(tagged_phrase, TDC.type)
    #         closest.append((p,t))

    #         # if 1 < i < len(self.TDC_collection.TDCs):
    #         #     print("\n and \n")
    #     return closest

    # def find_closest_phrase(self, tagged_phrase, template_type):
    #     """Find closest matching template phrases to input phrase.
    #     """
    #     # For each tagged word (word span) in the tagged phrase
    #     #<>TODO: break the independence assumption! We're assuming SRs and
    #     # Groundings are independent of one-another, for instance. Not true!            
    #     template = self.phrase_templates[template_type].copy()
    #     for tagged_word_span in tagged_phrase:
    #         tag = tagged_word_span[1]
    #         word_span = tagged_word_span[0]
    #         if tag == 'NULL':
    #             continue

    #         closest_word = self.find_closest_word(tag, word_span)
    #         template[tag] = closest_word

    #     # Delete empty values
    #     for key, value in template.iteritems():
    #         if value == '':
    #             del template[key]

    #     phrase = template_to_string(template)

    #     return phrase, template

    # def find_closest_word(self, tag, word_span):
    #     """Find the closest template word to an individual word-span, given a tag.
    #     """
    #     similarities = []

    #     for template_word in self.templates[tag]:
    #         tw = self.nlp(unicode(template_word))
    #         ws = self.nlp(unicode(word_span.replace('_',' ')))
    #         s = tw.similarity(ws)
    #         similarities.append(s)

    #     ranked_template_words = [x for (y,x) in 
    #         sorted(zip(similarities, self.templates[tag]), reverse=True)]

    #     logging.debug("\nSimilarity to '{}'".format(word_span))
    #     for word, similarity in zip(self.templates[tag], similarities):
    #         logging.debug("\t\t'{}': {}".format(word, similarity))
    #     return ranked_template_words[0]

def template_to_string(template):
    print template
    str_ = " ".join(filter(None, template.values()[:-1]))
    str_ += template.values()[-1]
    return str_

def test_matcher():
    # from cops_and_robots.human_tools.nlp.templater import test_TDC_collection

    # filled_templates = test_TDC_collection()
    # filled_template = filled_templates[2]
    labeled_utterances = []
    labeled_utterance = OrderedDict([('certainty', 'know'),
                                     ('target', 'a robot'),
                                     ('positivity', 'is'),
                                     ('spatial_relation:object', 'right of'),
                                     ('grounding:object', 'the bookcase')]
                                     )
    labeled_utterances.append(labeled_utterance)
    
    # labeled_utterance = OrderedDict([('certainty', 'know'),
    #                                  ('target', 'a robot'),
    #                                  ('positivity', 'is'),
    #                                  ('spatial_relation:object', 'next to'),
    #                                  ('grounding:object', 'the bookcase')]
    #                                  )
    # labeled_utterances.append(labeled_utterance)

    # labeled_utterance = OrderedDict([('certainty', 'know'),
    #                                  ('target', 'a robot'),
    #                                  ('positivity', "isn't"),
    #                                  ('spatial_relation:object', 'next to'),
    #                                  ('grounding:object', 'the bookshelf')]
    #                                  )
    # labeled_utterances.append(labeled_utterance)

    # labeled_utterance = OrderedDict([('certainty', 'am pretty sure'),
    #                                  ('target', "one of those guys"),
    #                                  ('positivity', "is"),
    #                                  ('spatial_relation:object', 'somewhere close to'),
    #                                  ('grounding:object', 'that pile of books')]
    #                                  )
    # labeled_utterances.append(labeled_utterance)



    # # labeled_utterance = OrderedDict([('certainty', 'know'),
    # #                                  ('target', 'a robot'),
    # #                                  ('positivity', 'is'),
    # #                                  ('spatial_relation:object', 'behind'),
    # #                                  ('grounding:object', 'the checkers table')]
    # #                                  )
    # # labeled_utterances.append(labeled_utterance)
    
    # # labeled_utterance = OrderedDict([('certainty', 'know'),
    # #                                  ('target', 'a robot'),
    # #                                  ('positivity', 'is'),
    # #                                  ('spatial_relation:area', 'at the end of'),
    # #                                  ('grounding:area', 'the hallway')]
    # #                                  )
    # # labeled_utterances.append(labeled_utterance)

    # # labeled_utterance = OrderedDict([('certainty', 'know'),
    # #                                  ('target', 'the red one'),
    # #                                  ('positivity', "is"),
    # #                                  ('spatial_relation:object', 'behind'),
    # #                                  ('grounding:object', 'the filing cabinet')]
    # #                                  )
    # # labeled_utterances.append(labeled_utterance)

    # # labeled_utterance = OrderedDict([('certainty', 'there might be'),
    # #                                  ('target', "someone"),
    # #                                  ('positivity', "is"),
    # #                                  ('spatial_relation:object', 'in the'),
    # #                                  ('grounding:object', 'hallway')]
    # #                                  )
    # # labeled_utterances.append(labeled_utterance)


    matcher = Matcher()

    # show_n = 5

    from cops_and_robots.map_tools.map import Map, set_up_fleming
    from cops_and_robots.fusion.gaussian_mixture import fleming_prior
    from cops_and_robots.map_tools.probability_layer import ProbabilityLayer
    from cops_and_robots.fusion.gauss_sum_filter import GaussSumFilter
    from cops_and_robots.robo_tools.cop import Cop
    from cops_and_robots.robo_tools.robber import Robber
    from cops_and_robots.human_tools.human import Human
    import matplotlib.pyplot as plt

    # fig = plt.figure()
    # ax = fig.add_subplot(111)
    roy = Robber('Roy', pose=[-0.3,-2,90])
    deckard = Cop('Deckard', other_robot_names={'robbers':['Roy']})
    map_ = Map()
    map_.add_cop(deckard.map_obj)
    map_.add_robber(roy.map_obj)
    human_sensor = Human(map_=map_)

    geometric_filter = GaussSumFilter(compression_method='geometric',
                                      target_name='Roy',
                                      fusion_method='sequential',
                                      dynamic_model=False,
                                      )
    class FFE(object):
        def __init__(self, filter_):
            self.filters = {'Roy':filter_}
    fake_fusion_engine = FFE(geometric_filter)
    map_.plot(fusion_engine=fake_fusion_engine)

    prior = fleming_prior()
    # matcher.find_nearest_statements(filled_templates)
    for labeled_utterance in labeled_utterances:
        statement = matcher.compare_slots(labeled_utterance, show_n=5)
        human_sensor.statement = statement
        geometric_filter.probability = prior.copy()
        geometric_filter.fusion(human_sensor)
        map_.plot(fusion_engine=fake_fusion_engine)

    # for _, statement in statements.iteritems():
    #     for s in statement:
    #         print s





if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    test_matcher()

    # phrase,_ = sc.find_closest_phrase(tagged_phrase, template_type)
    # print phrase