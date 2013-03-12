from setuptools import setup, find_packages

setup(
    name='formtags',
    version='1.2',

    packages=find_packages(),

    install_requires=['django'],

    author='Sofokus',
    author_email='calle.laakkonen@sofokus.com',
    description='A form rendering tag library for Django templates',
    license='MIT',
    keywords='django, form',
    url='https://github.com/Sofokus/formtags',

)

