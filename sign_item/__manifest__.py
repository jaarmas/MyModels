{
    'name': 'Relate Sign Item Type and IR Sequence',
    'version': '1.0',
    'author': 'Jorge Armas',
    'category': 'Tools',
    'summary': 'Relate Sign Item Type and IR Sequence',
    'description': """
        This module adds a field to relate Sign Item Type with IR Sequence.
    """,
    'depends': ['base', 'sign'],
    'data': [
        'data/custom_sequence_data.xml',
        'views/sign_item_type_sequence.xml',
    ],

    'installable': True,
    
    'assets': {
        'web.assets_common': [
            'sign_item/static/src/js/common/*',
            'sign_item/static/src/xml/*',
        ],
        'web.assets_frontend': [
            'sign_item/static/src/js/common/*',
        'sign_item/static/src/xml/*',
        ]
    }
}
