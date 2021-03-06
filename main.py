from fuzzywuzzy import fuzz, process
import json
import requests
import sqlite3


from db_setup import create_food_tables


class Client:
    """
    The API client with all 4 endpoints (ep) to the USDA NDB API: 1) food_report, 2) list, 3) nutrients, 4) search
    For more information on the request parameters and response body, read the documentation of the USDA NDB API at:
    https://ndb.nal.usda.gov/ndb/api/doc

    Alternatively, full db dumps are available in ASCII and Microsoft Access files at:
    https://www.ars.usda.gov/northeast-area/beltsville-md/beltsville-human-nutrition-research-center/nutrient-data-laboratory/docs/sr28-download-files/
    """

    BASE_URL = 'https://api.nal.usda.gov/ndb'
    FORMAT = 'json'

    def __init__(self, api_key):
        self.api_key = api_key

    def food_report(self, ndbno, type='f', **kwargs):
        """
        Return a list of USDA nutrient (USDA food ID, USDA nutrient ID, value per 100g, unit) tuples,

        API documentation for the food_report endpoint, including parameters can be found at:
        https://ndb.nal.usda.gov/ndb/doc/apilist/API-FOOD-REPORTV2.md
        """

        kwargs.update({'ndbno': ndbno, 'type': type})
        data = self._call('V2/reports', **kwargs)

        nutrient_ids_values = [(ndbno,
                                data['foods'][0]['food']['nutrients'][i]['nutrient_id'],
                                data['foods'][0]['food']['nutrients'][i]['value'])
                               for i in range(len(data['foods'][0]['food']['nutrients']))]

        return nutrient_ids_values

    def list(self, **kwargs):
        return self._call('list', **kwargs)

    def nutrients(self, **kwargs):
        return self._call('nutrients', **kwargs)

    def search(self, q, ds='Standard Reference', sort='n', originalq=None, **kwargs):
        """
        Return selected food's USDA food database ID (ndbno).

        API documentation for the search endpoint, including parameters can be found at:
        https://ndb.nal.usda.gov/ndb/doc/apilist/API-SEARCH.md
        """

        kwargs.update({'ds': ds, 'q': q, 'sort': sort})
        data = self._call('search', **kwargs)

        def prompt(top_choices):
            try:
                match = int(input('\n Please select the matching food for {0} (0-4):'.format(q)))

                # get ndbo code associated with the fuzzy-matched food
                #if match is last in list, rerun choices
                i = top_choices[match][0][1]
                ndbno = (data['list']['item'][i]['ndbno'])

                if originalq:
                    return (ndbno, originalq)

                return (ndbno, q)

            except:
                print('Please enter a valid input. Input must be a number 0-{0}'.format(len(top_choices)))
                return prompt(top_choices)

        def choices():
            # fuzzy match food name
            try:
                choices = [(data['list']['item'][i]['name'], i) for i in range(len(data['list']['item']))]
                top_choices = process.extract(q, choices, scorer=fuzz.token_sort_ratio, limit=5)

                for i, option in enumerate(top_choices):
                    print(i, option[0][0])
                # print(len(top_choices), 'more options')

                return prompt(top_choices)

            except TypeError as e:
                if 'NoneType' in str(e):
                    print('Call failed. Please confirm that your API is correct and that your parameter inputs are allowed.'
                          'You entered the following parameters: ', kwargs,
                          '.\nSee the documentation at https://ndb.nal.usda.gov/ndb/doc/apilist/API-SEARCH.md'
                          'for a list of accepted parameters. ')
            except (IndexError, KeyError):
                print("No search results found for: {0}.".format(q))
                replacement_y_n = input('\n Would you like to try a replacement term? (Y/N): ')
                if replacement_y_n.lower() in ['y', 'yes']:
                    replacement_term = input('\n What new term would you like to use?: ')
                    if originalq:
                        return client.search(replacement_term, originalq=originalq)
                    else:
                        return client.search(replacement_term, originalq=q)
        return choices()

    def _call(self, ep, **kwargs):
        url = '{0}/{1}'.format(self.BASE_URL, ep)
        kwargs.update({'format': self.FORMAT, 'api_key': self.api_key})

        try:
            response = requests.get(url, params=kwargs)
            if response.status_code != 200:
                raise requests.exceptions.HTTPError
            odict_response = json.loads(response.text)
            return odict_response
        except requests.exceptions.RequestException as e:
            print('Uh oh: ', e)

    def add_food(self, ndbno_term):
        if ndbno_term is not None:
            ndbno = ndbno_term[0]
            term = ndbno_term[1]
            with sqlite3.connect('food_db.db') as conn:
                c = conn.cursor()

                try:
                    c.execute('INSERT INTO usda_food_mapping (usda_food_id, food_name) VALUES (?, ?)', (ndbno, term))
                except sqlite3.IntegrityError as e:
                    if 'usda_food_mapping.food_name' in str(e):
                        c.execute('UPDATE usda_food_mapping SET usda_food_id = ? WHERE food_name = ?', (ndbno, term))
                        print('Food ID updated')
                    elif 'usda_food_mapping.usda_food_id' in str(e):
                        c.execute('UPDATE usda_food_mapping SET food_name = ? WHERE usda_food_id = ?', (term, ndbno))
                        print('Food name updated')
                    else:
                        raise e

    def add_food_nutrients(self, nutrient_ids_values):
        with sqlite3.connect('food_db.db') as conn:
            c = conn.cursor()

            for i in nutrient_ids_values:
                try:
                    # todo If ndbno associated with a food's name is changed, this will succeed, when it should...
                    # todo ...update the previous entry based on the food's name.
                    c.execute('INSERT INTO food_nutrient (usda_food_id, usda_nutrient_id, nutrient_value)'
                              'VALUES (?, ?, ?)', (i[0], i[1], i[2]))
                except sqlite3.IntegrityError:
                    c.execute('UPDATE food nutrient '
                              'SET nutrient_value = ?,'
                              'WHERE usda_food_id = ?, usda_nutrient_id = ?', (i[2], i[0], i[1]))

                    print('Food\'s nutrient values updated')

if __name__ == "__main__":
    client = Client('<YOUR API KEY GOES HERE>')

    # create tables
    create_food_tables()

    # your code goes here