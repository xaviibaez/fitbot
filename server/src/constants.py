LOGIN_ENDPOINT = "https://login.aimharder.com/api/login"


def book_endpoint(box_name):
    return f"https://{box_name}.aimharder.com/api/book"


def cancel_endpoint(box_name):
    return f"https://{box_name}.aimharder.com/api/cancelBook"


def classes_endpoint(box_name):
    return f"https://{box_name}.aimharder.com/api/bookings"
