import telebot
from telebot import types
import requests
import atexit
import pickle
from threading import Thread
import traceback
import sys
import time


def run(func):
    func()
    return func

threaded_runs = []

def run_threaded(func):
    def threaded_call(*argc,**argv):
        def call():
            func(*argc,**argv)
            
        t = Thread(target=call)
        t.start()
    return threaded_call

def catch_errors_on_command(func):
    def err_catcher(message,*argc,**argv):
        try:
            func(message,*argc,**argv)
        except BaseException as e:
            traceback.print_exception(*sys.exc_info())
            bot.send_message(message.from_user.id, text=f'Ошибка: {e}')
    return err_catcher


help_string = ""
commands_callbacks = dict()
bot_commands = []

def register_command(name,description):
    global help_string
    command = types.BotCommand(f'/{name}',f'{description}')
    help_string=f"{help_string}\n/{name} - {description}"
    bot_commands.append(command)
    def register(func):
        commands_callbacks[name]=func
        return func
    
    return register

def make_command_remove_message(func):
    def callback(message,*arg,**kwarg):
        func(message,*arg,**kwarg)
        bot.delete_message(message.chat.id,message.message_id)
        
    return callback

# Создаем экземпляр бота
bot = telebot.TeleBot(open("token.txt","r").read())

def write_user_data():
    with open("users.pickle","wb") as f:
        pickle.dump(users,f)

    

try:
    with open("users.pickle","rb") as f:
        users = pickle.load(f)
except Exception as e:
    print(e)
    users = dict()
    
if users is None:
    users = dict()

def get_user_data(message):
    return users[message.from_user.username]

@register_command("mode","set used mode")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def mode(message):
    keyboard = types.InlineKeyboardMarkup()
    key_continue = types.InlineKeyboardButton(text='continue', callback_data='mode.continue')
    key_chat = types.InlineKeyboardButton(text='chat', callback_data='mode.chat')
    key_1resp = types.InlineKeyboardButton(text='1 query 1 response', callback_data='mode.new_msg')
    key_simple_continue = types.InlineKeyboardButton(text='continue_simple', callback_data='mode.continue_simple')
    keyboard.add(key_continue)
    keyboard.add(key_chat)
    keyboard.add(key_1resp)
    keyboard.add(key_simple_continue)
    bot.send_message(message.from_user.id, text='select mode', reply_markup=keyboard)
    
@register_command("model","choose model")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def model(message):
    url = settings['url']+'internal/model/list'
    response = requests.get(url, verify=False)
    try:
        models = response.json()['model_names']
        keyboard = types.InlineKeyboardMarkup()
        for model in models:
            key = types.InlineKeyboardButton(text=f'{model}', callback_data=f'model.{model}')
            keyboard.add(key)
        bot.send_message(message.from_user.id, text='Select model:', reply_markup=keyboard)
    except Exception as e:
        bot.send_message(message.from_user.id, text=f'unknown error: {e}, api answer: {response}')
    
    pass

@register_command("unload","unload model")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def unload(message):
    url = settings['url']+'internal/model/unload'
    response = requests.post(url, verify=False)
    if(not response.status_code==200):
        bot.send_message(message.from_user.id, text=f'fail: {response}')
    else:
        bot.send_message(message.from_user.id, text=f'unloaded')
        
        
@register_command("response_size","sets size of response")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def set_size(message):
    keyboard = types.InlineKeyboardMarkup()
    for size in [50,100,200,400,500,800,1024,1600,2048,4096]:
        key = types.InlineKeyboardButton(text=f'{size}', callback_data=f'size.{size}')
        keyboard.add(key)
    bot.send_message(message.from_user.id, text='Select response size:', reply_markup=keyboard)
    
@register_command("profile","get user profile")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def profile(message):
    user_data = get_user_data(message)
    response = f'''
    {user_data}
'''
    bot.send_message(message.from_user.id, text=response)
    
@register_command("reset","reset context")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def profile(message):
    user_data = get_user_data(message)
    user_data['history']=[]
    bot.send_message(message.from_user.id, text='context dropped')

@register_command("help","show help mesage")
@make_command_remove_message
@run_threaded
@catch_errors_on_command
def help(message):
    bot.send_message(message.chat.id, help_string)
    
        
def process_command(message):
    if(message.text[0]!='/'):
        return False
    cmd = message.text[1:max(len(message.text),message.text.find(' '))]
    if cmd in commands_callbacks:
        callback = commands_callbacks[cmd]
        callback(message)
        return True
            
    return False
        
@run_threaded
@catch_errors_on_command
def generate(message):
    url = settings['url']+'chat/completions'
    headers = {
        "Content-Type": "application/json"
    }

    user_data = get_user_data(message)
    history:any
    if('history' in user_data):
        history=user_data['history']
    else:
        history=[]
        user_data['history']=history
        
    if(user_data['mode'] in ['new_msg','continue_simple'] ):
        history=[]
        
        
    if(user_data['mode'] in ['continue','continue_simple']):
        history.append({"content": message.text})
    else:
        history.append({"role": "user", "content": message.text})
    
    

    
    data = {
        "max_tokens":200 if not 'response_size' in user_data else user_data['response_size'],
        #"mode": "chat" if user_data['mode'] in ['chat','new_msg'] else 'continue',
        "mode": "chat",
        "character": "Assistant",
        "messages": history
    }
    
    @run_threaded
    def msg_generating(mesage):
        bot.send_message(message.from_user.id, text=f'generating')  
        
    msg_generating(message)

    response = requests.post(url, headers=headers, json=data, verify=False)
    assistant_message = response.json()['choices'][0]['message']['content']
    history.append({"role": "assistant", "content": assistant_message})
    print(assistant_message)
    def send_message_garanteed(text=''):
        while True:
            try:
                bot.send_message(message.from_user.id, text=text)  
                return
            except:
                time.sleep(5)
    if(len(assistant_message)<4000):
        send_message_garanteed(text=f'{assistant_message}')    
    else:
        msg = ""
        for part in assistant_message.split('\n'):
            if(len(msg)+len(part)>4000):
                send_message_garanteed(text=f'{msg}') 
                msg = part
            else:
                msg+='\n'
                msg+=part
        if(len(msg)>3):
            send_message_garanteed(text=f'{msg}') 
    
@run
def load_settings():
    global settings 
    global elevated_users
    settings = eval(open("settings.py","r").read())
    elevated_users = settings["elevated_users"]
# Функция, обрабатывающая команду /start
@bot.message_handler(commands=["start"])
def start(m, res=False):
    print(m)
    # записать пользователя прям сразу тут в users

    bot.send_message(m.chat.id, 'Hello')
# Получение сообщений от юзера
@bot.message_handler(content_types=["text"])
def handle_text(message):
    user = message.from_user.username
    if(message.from_user.username not in elevated_users):
        print(f"incorrect username: {message.from_user.username}")
        return
    user_data:any
    if not user in users:
        user_data = dict()
        users[user]=user_data
    else:
        user_data = users[user]
    
    if(message.text.startswith('/')):
        if(not process_command(message)):
            bot.send_message(message.from_user.id, f'Unknown command: {message.text}')
        return
    
        
    if(not 'mode' in user_data):
        user_data['mode']='chat'
    
    generate(message)

bot.set_my_commands(bot_commands)   

@bot.callback_query_handler(func=lambda call: True)
def callback_worker(call):
    user_data = get_user_data(call)
    data:str = call.data
    mode = data.split('.')
    category = mode[0]
    match category:
        case 'mode':
            type = mode[1]
            if(not 'mode' in user_data):
                user_data['mode']='none'
            if(user_data['mode']!=type):
                user_data['mode']=type
                user_data['history']=[]
                bot.send_message(call.from_user.id,"new mode: %s"%type)
        case 'model':
            model = data[data.find('.')+1:]
            url = settings['url']+'internal/model/load'
            data = {
            "model_name":model
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            response = requests.post(url, json=data,headers=headers,verify=False)
            if(response.status_code==200):
                bot.send_message(call.from_user.id,"model loaded: %s"%model)
            else:
                bot.send_message(call.from_user.id,f"failed to load model {response}")
        case 'size':
            user_data['response_size']=int(mode[1])
            bot.send_message(call.from_user.id,f"New response size: {mode[1]}")
    bot.delete_message(call.message.chat.id,call.message.message_id)


@atexit.register
def exit_handler():
    write_user_data()
        
@run
@run_threaded
def run_bot():         
    bot.infinity_polling(timeout=10, long_polling_timeout = 5)


def main():
    
    while True:
        msg = input('>')
        print(msg)
        
if __name__=='__main__':
    main()