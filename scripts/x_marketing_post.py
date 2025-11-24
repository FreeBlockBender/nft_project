from app.utils.x_functions import format_marketing_x_post, post_to_x

def main(): 
    message = format_marketing_x_post()
    post_to_x(message)

if __name__ == "__main__":
    main()

