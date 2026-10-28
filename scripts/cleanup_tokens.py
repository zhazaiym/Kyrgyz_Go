from mysite.api.token_maintenance import cleanup_expired_tokens

if __name__ == '__main__':
    print(cleanup_expired_tokens())
