#!/usr/bin/python3

from flask import Flask, render_template, request, redirect, url_for
from wtforms import Form, SelectField, StringField, validators
from scraper import Scraper


app = Flask(__name__)

scraper = Scraper()


class CategoryForm(Form):
    category = SelectField('News category', validators=[validators.InputRequired])


class TokenForm(Form):
    text = StringField('Text search', validators=[validators.InputRequired])


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/category_search', methods=['GET', 'POST'])
def category_search():
    categories = scraper.tsn_categories()
    categories += scraper.ukrnet_categories()
    category_list = [c['name'] for c in categories]
    form = CategoryForm(request.form)
    form.category.choices = category_list

    if request.method == 'POST' and form.validate():
        category_choice = form.category.data
        result = scraper.search_by_category(category_choice, categories)
        return render_template('news_result.html', content=result)
    return render_template('category_search.html', form=form)


@app.route('/text_search', methods=['GET', 'POST'])
def text_search():
    form = TokenForm(request.form)
    if request.method == 'POST' and form.validate():
        searched_text = request.form['token']

        result = scraper.search_by_text(searched_text, searched_text)
        return render_template('news_result', content=result)
    return render_template('text_search.html', form=form)


if __name__ == '__main__':
    app.run(debug=True)



# export FLASK_APP=app.py
# export FLASK_DEBUG=1
# export LANG=ru_RU.UTF-8
# export LC_CTYPE=ru_RU.UTF-8
# flask run


