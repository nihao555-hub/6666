# Alibaba Search Ranking And Keyword Decisions

Use this reference when interpreting Alibaba ICBU ranking, order potential, keyword data, SKU depth, or category priority.

## Search Logic

Treat Alibaba search as three gates:

1. compliance and anti-spam filtering
2. matching between buyer query and product/category/attributes/images
3. ranking by buyer behavior, product quality, and supplier quality signals

Operational meaning:

- first survive quality and compliance filters
- then make the listing unmistakably match the searched product
- only then compete on click, inquiry, and supplier strength

Important assumptions:

- search is buyer-led, not seller-led
- first-page exposure is limited
- not every published SKU has equal ranking opportunity
- repeated blind reposting is weaker than quality and concentration
- similar products inside one account can compete with each other when differentiation is thin

## Data Reading Order

Analyze in this order:

1. Platform rule layer: category, title, attributes, image fit, quality rules, and import restrictions
2. Market heat layer: search index, search growth, click rate, and seller-size index
3. Store traction layer: exposure, clicks, valid product count, premium products, and hot products
4. Supply-fit layer: whether the supplier can actually deliver the product, specs, customization, packing, and export support
5. Publishing decision layer: publish now, test carefully, support only, or avoid now

Do not make a publishing decision from hot-term data alone.

## Metric Interpretation

- `high search + clear product word + good click behavior`: strong candidate for a main or growth line
- `high search + broad generic word`: risky by itself; likely noisy traffic
- `high click rate + moderate seller density`: often worth testing if supply fit is real
- `traffic exists but premium products are low and hot products are zero`: weak traffic concentration, not necessarily no demand
- `category prediction and store data mismatch the real product`: usually category-expression mismatch, not proof that the product has no demand

Useful metrics:

- `search index`: demand size
- `search growth`: short-term trend
- `click rate`: buyer interaction strength
- `seller-size index`: competition density
- `store exposure/click`: current traction
- `valid/premium/hot product counts`: quality concentration inside the account

## Keyword Priority

Prefer keywords that are:

- product-specific
- supply-capability matched
- inquiry-friendly
- category-clean
- usable with real images and attributes

Classify keywords:

- `S priority`: strong supply fit and clear order intent
- `A priority`: good test terms if product proof and images are real
- `B priority`: support, package traffic, or long-tail coverage
- `C priority`: avoid due to weak fit, noisy traffic, unverifiable claims, or category risk

## SKU Depth

Separate published SKU count from core-ranking SKU count.

Default ranges:

- main traffic categories: publish `24-36`, core-ranking pool `8-12`
- support or inquiry categories: publish `18-24`, core-ranking pool `6-8`
- OEM filter categories: publish `12-18`, core-ranking pool `4-6`
- image or high-ticket categories: publish `12-18`, core-ranking pool `3-5`

A practical 30-SKU batch often uses `5 keyword clusters x 6 scenarios`, but the clusters and scenarios must represent real buyer differences.
