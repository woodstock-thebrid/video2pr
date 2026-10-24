from copy import deepcopy


_MOCK_BUGS: dict[str, dict[str, object]] = {
    "burger": {
        "report": {
            "title": "Tech Tower Burger quantity is omitted from the subtotal",
            "page": "GT Dining order page — Your Order cart",
            "steps": [
                "Open GT Dining and add two Tech Tower Burgers using the + control.",
                "Check the cart quantity, subtotal, tax, and total.",
            ],
            "expected": "Two Tech Tower Burgers at $12.50 each should produce a $25.00 subtotal, $2.23 tax, and $27.23 total.",
            "actual": "The cart shows quantity 2, but Subtotal is $12.50, Tax is $1.11, and Total is $13.61.",
            "suspected_area": "The subtotal calculation in demo-app/app.js charges one burger instead of multiplying the Tech Tower Burger price by its quantity.",
            "severity": "medium",
        },
        "root_cause": "The burger subtotal calculation omitted quantity when computing the line total.",
        "code_diff": (
            "-    return sum + item.price * (id === \"burger\" ? 1 : quantity);\n"
            "+    return sum + item.price * quantity;"
        ),
        "before_url": "/mock/before.png",
        "after_url": "/mock/after.png",
    },
    "search": {
        "report": {
            "title": "Multi-word menu searches hide matching items",
            "page": "GT Dining home page — Made for your day menu",
            "steps": [
                "Open the GT Dining menu and locate Search the menu.",
                "Type chicken and confirm Chicken Tenders ($10.25) appears.",
                "Continue the query to chicken tenders.",
            ],
            "expected": "Chicken Tenders ($10.25) should remain visible for the exact multi-word search chicken tenders.",
            "actual": "Typing chicken tenders empties the menu and shows No menu items match that search, even though searching chicken finds Chicken Tenders.",
            "suspected_area": "The search-term normalization in demo-app/app.js removes spaces before matching the full query against the item name.",
            "severity": "medium",
        },
        "root_cause": "The search handler removed whitespace from the query but not from menu item names, so multi-word item names could not match.",
        "code_diff": (
            "-  const normalizedTerm = searchTerm.toLowerCase().replace(/\\s/g, \"\");\n"
            "+  const normalizedTerm = searchTerm.toLowerCase().trim().replace(/\\s+/g, \" \");"
        ),
        "before_url": "/mock/search-before.png",
        "after_url": "/mock/search-after.png",
    },
    "double_order": {
        "report": {
            "title": "Rapid double-click on Checkout places two orders",
            "page": "GT Dining home page — Your Order checkout panel",
            "steps": [
                "Add a Tech Tower Burger ($12.50) to Your Order.",
                "Double-click Checkout rapidly.",
                "Read the order confirmation number.",
            ],
            "expected": "One checkout action should place one order and advance the order number once.",
            "actual": "A rapid double-click runs the checkout handler twice; the confirmation advances by two order numbers and two orders are placed.",
            "suspected_area": "The checkout click handler in demo-app/app.js has no in-flight guard, so both click events increment the order counter.",
            "severity": "high",
        },
        "root_cause": "The checkout handler accepts each click independently and increments the persisted order counter twice during a rapid double-click.",
        "code_diff": (
            "+let checkoutInProgress = false;\n"
            " document.querySelector(\"#checkout\").addEventListener(\"click\", () => {\n"
            "+  if (checkoutInProgress) return;\n"
            "+  checkoutInProgress = true;\n"
            "   const count = Number(localStorage.getItem(\"gt-dining-orders\") || 0) + 1;\n"
            "+  setTimeout(() => { checkoutInProgress = false; }, 1000);"
        ),
        "before_url": "/mock/double-before.png",
        "after_url": "/mock/double-after.png",
    },
    "mobile_checkout": {
        "report": {
            "title": "Fixed mobile banner covers the Checkout button below 420px",
            "page": "GT Dining order page — Your Order card at 390×844",
            "steps": [
                "Set the viewport to a narrow phone width below 420px, such as 390×844.",
                "Add a Tech Tower Burger ($12.50) and scroll to the Your Order card.",
                "Try to tap Checkout.",
            ],
            "expected": "The Checkout button should remain fully visible and tappable above the fixed gold banner.",
            "actual": "The fixed gold banner overlaps the Checkout button at the bottom of the screen and intercepts taps.",
            "suspected_area": "The max-width:420px positioning rules for .checkout-button and .mobile-banner in demo-app/styles.css.",
            "severity": "high",
        },
        "root_cause": "On narrow screens the checkout button is fixed 12px from the bottom, underneath the 72px fixed gold banner.",
        "code_diff": (
            "@media(max-width:420px){.cart-card .checkout-button{\n"
            "-  bottom:12px;\n"
            "+  bottom:84px;\n"
            "}}"
        ),
        "before_url": "/mock/mobile-before.png",
        "after_url": "/mock/mobile-after.png",
    },
}


def mock_bug_for_upload(upload_name: str | None) -> dict[str, object]:
    name = (upload_name or "").lower()
    if "search" in name:
        bug_key = "search"
    elif "double" in name or "order" in name:
        bug_key = "double_order"
    elif "mobile" in name or "checkout" in name:
        bug_key = "mobile_checkout"
    else:
        bug_key = "burger"
    return deepcopy(_MOCK_BUGS[bug_key])
