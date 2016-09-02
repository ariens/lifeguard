"""
Lifeguard
---------

TODO
    Docs
"""

from setuptools import setup, find_packages

setup(
    name='lifeguard',
    version='0.1.11',
    url='https://gitlab.rim.net/ipgbd-software/lifeguard-webapp',
    description='Web based management of pools of servers',
    long_description=__doc__,
    license='Apache 2.0',
    author='Dave Ariens',
    author_email='dariens@blackberry.com',
    packages=find_packages(),
    include_package_data=True,
    install_requires=["click==6.6",
                      "dnspython==1.15.0",
                      "Flask==0.11.1",
                      "Flask-Login==0.3.2",
                      "Flask-WTF==0.12",
                      "jira==1.0.3",
                      "ldap3==1.3.1",
                      "oauthlib==1.1.2",
                      "pyasn1==0.1.9",
                      "PyMySQL==0.7.4",
                      "pytz==2016.4",
                      "requests==2.10.0",
                      "requests-oauthlib==0.6.1",
                      "requests-toolbelt==0.6.2",
                      "six==1.10.0",
                      "SQLAlchemy==1.0.13",
                      "tlslite==0.4.9",
                      "uWSGI==2.0.13.1",
                      "WTForms==2.1", ],
    package_data={
        'templates': 'lifeguard/templates/*',
        'static': 'lifeguard/static/*',
    },
    entry_points={
        'console_scripts': [
            'health_tasks = lifeguard.bin.health_tasks:run',
            'process_tickets = lifeguard.bin.process_tickets:run',
        ]
    }
)
