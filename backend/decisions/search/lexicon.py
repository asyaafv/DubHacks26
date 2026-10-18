"""Query understanding: map search terms to MCC groups with friendly labels.

This table maps *queries* to merchant-category codes (greggles/mcc-codes, the
same taxonomy as shared/seed/seed_merchants.json). It never produces results by
itself: matched MCCs are intersected with the user's own rewards, so everything
returned comes from their wallet data.
"""

RESTAURANTS = frozenset({'5812', '5813', '5814'})
GROCERY = frozenset({'5411', '5422', '5441', '5451', '5462', '5921'})
CLOTHING = frozenset({'5611', '5621', '5631', '5641', '5651', '5691', '5699'})
SHOES = frozenset({'5661'})
ELECTRONICS = frozenset({'5045', '5732', '5734'})
BEAUTY = frozenset({'5977', '7230'})
PHARMACY = frozenset({'5122', '5912'})
FURNITURE = frozenset({'5021', '5712', '5713', '5714', '5719'})
HOME_IMPROVEMENT = frozenset({'5200', '5211', '5251'})
DEPARTMENT = frozenset({'5311'})
WHOLESALE = frozenset({'5300'})
BOOKS = frozenset({'5192', '5942'})
MARKETPLACE = frozenset({'5999'})

FOOD = RESTAURANTS | GROCERY
STREETWEAR = CLOTHING | SHOES
HOME = FURNITURE | HOME_IMPROVEMENT


def _expand(label, mccs, *terms):
    return {term: (label, mccs) for term in terms}


# term (token or bigram) -> (label for match reasons, MCC group)
KEYWORD_MCCS: dict[str, tuple[str, frozenset[str]]] = {
    **_expand('food & dining', FOOD, 'food', 'foods', 'hungry', 'snack', 'snacks'),
    **_expand('restaurants', RESTAURANTS,
              'restaurant', 'restaurants', 'dining', 'dinner', 'lunch', 'breakfast',
              'brunch', 'meal', 'meals', 'takeout', 'take out', 'delivery', 'eat', 'eats',
              'fast food', 'eating out'),
    **_expand('Mexican food', RESTAURANTS,
              'mexican', 'mexican food', 'taco', 'tacos', 'burrito', 'burritos',
              'quesadilla', 'guacamole', 'guac', 'salsa', 'nachos'),
    **_expand('pizza & Italian', RESTAURANTS, 'pizza', 'italian', 'pasta'),
    **_expand('fast food', RESTAURANTS,
              'burger', 'burgers', 'fries', 'chicken', 'nuggets', 'sandwich',
              'sandwiches', 'sub', 'subs', 'wings'),
    **_expand('coffee & cafes', RESTAURANTS,
              'coffee', 'latte', 'espresso', 'cafe', 'tea', 'donut', 'donuts', 'bakery',
              'boba', 'smoothie'),
    **_expand('groceries', GROCERY, 'grocery', 'groceries', 'supermarket', 'produce'),
    **_expand('clothing', CLOTHING,
              'clothing', 'clothes', 'apparel', 'fashion', 'outfit', 'outfits',
              'wardrobe', 'dress', 'dresses', 'shirt', 'shirts', 'pants'),
    **_expand("men's clothing", CLOTHING,
              'mens', 'men', 'menswear', 'mens clothing', 'men clothing'),
    **_expand("women's clothing", CLOTHING, 'womens', 'women', 'womenswear'),
    **_expand('streetwear', STREETWEAR,
              'streetwear', 'street wear', 'sneaker', 'sneakers', 'kicks', 'hoodie',
              'hoodies', 'jeans', 'denim', 'tees', 'athleisure'),
    **_expand('shoes', SHOES, 'shoe', 'shoes', 'footwear', 'boots', 'running shoes'),
    **_expand('electronics', ELECTRONICS,
              'electronics', 'electronic', 'tech', 'gadget', 'gadgets', 'laptop',
              'computer', 'computers', 'phone', 'phones', 'tv', 'headphones'),
    **_expand('beauty', BEAUTY,
              'beauty', 'makeup', 'cosmetics', 'skincare', 'fragrance', 'perfume',
              'lotion', 'shampoo'),
    **_expand('pharmacy', PHARMACY,
              'pharmacy', 'drugstore', 'medicine', 'vitamins', 'health'),
    **_expand('home & furniture', HOME,
              'home', 'furniture', 'sofa', 'couch', 'decor', 'home goods'),
    **_expand('home improvement', HOME_IMPROVEMENT,
              'hardware', 'tools', 'garden', 'home improvement', 'diy'),
    **_expand('department stores', DEPARTMENT, 'department', 'department store',
              'department stores'),
    **_expand('wholesale clubs', WHOLESALE, 'wholesale', 'bulk', 'warehouse club'),
    **_expand('books', BOOKS, 'book', 'books', 'bookstore', 'reading'),
    **_expand('online marketplaces', MARKETPLACE, 'marketplace', 'thrift', 'resale'),
}

# Quick-search chips, in display order. Only chips that match at least one of
# the user's eligible rewards are shown (see service.suggest_chips).
CHIP_DEFINITIONS: list[tuple[str, str, frozenset[str]]] = [
    ('Food', 'food', FOOD),
    ('Clothing', 'clothing', CLOTHING),
    ('Streetwear', 'streetwear', STREETWEAR),
    ('Shoes', 'shoes', SHOES),
    ('Electronics', 'electronics', ELECTRONICS),
    ('Beauty', 'beauty', BEAUTY),
    ('Home', 'home', HOME),
    ('Pharmacy', 'pharmacy', PHARMACY),
    ('Department stores', 'department stores', DEPARTMENT),
    ('Wholesale', 'wholesale', WHOLESALE),
    ('Books', 'books', BOOKS),
]
