TEXT = {
    'ru': {
        'heading': 'Проверьте заявку:',
        'labels': ['Имя', 'Телефон', 'Email'],
        'declined': 'Заявка не отправлена. Что хотите изменить или уточнить?',
        'submitted': 'Заявка отправлена менеджеру KYRGYZGO. Менеджер свяжется с вами для уточнения деталей.',
    },
    'en': {
        'heading': 'Please review your request:',
        'labels': ['Name', 'Phone', 'Email'],
        'declined': 'Your request has not been sent. What would you like to change or clarify?',
        'submitted': 'Your request has been sent to a KYRGYZGO manager. The manager will contact you to clarify the details.',
    },
    'ky': {
        'heading': 'Өтүнмөнүн маалыматтарын текшериңиз:',
        'labels': ['Аты', 'Телефон', 'Email'],
        'declined': 'Өтүнмө жөнөтүлгөн жок. Эмнени өзгөрткүңүз же тактагыңыз келет?',
        'submitted': 'Өтүнмө KYRGYZGO менеджерине жөнөтүлдү. Менеджер маалыматтарды тактоо үчүн сиз менен байланышат.',
    },
    'de': {
        'heading': 'Bitte prüfen Sie Ihre Anfrage:',
        'labels': ['Name', 'Telefon', 'E-Mail'],
        'declined': 'Ihre Anfrage wurde nicht gesendet. Was möchten Sie ändern oder klären?',
        'submitted': 'Ihre Anfrage wurde an das KYRGYZGO-Team gesendet. Das Team wird Sie kontaktieren, um die Details zu klären.',
    },
    'zh': {
        'heading': '请核对申请信息：',
        'labels': ['姓名', '电话', '邮箱'],
        'declined': '申请尚未发送。您希望修改或确认哪些信息？',
        'submitted': '申请已发送给 KYRGYZGO 客服。客服会联系您，核实详细信息。',
    },
}


def booking_text(data):
    language = data.get('language', 'ru')
    return TEXT.get(language, TEXT['en'])


def preview_text(data, choice):
    text = booking_text(data)
    # Trip requirements stay in the request, not in the contact confirmation.
    contacts = [(text['labels'][0], data['client_name']),
                (text['labels'][1], data['phone'])]
    if data.get('email'):
        contacts.append((text['labels'][2], data['email']))
    return text['heading'] + '\n' + '\n'.join(f'{label}: {value}' for label, value in contacts)
