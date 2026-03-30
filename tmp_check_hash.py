from werkzeug.security import generate_password_hash, check_password_hash
h = generate_password_hash('1234')
print(repr(h))
print(check_password_hash(h, '1234'))
