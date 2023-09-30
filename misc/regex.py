import json
import re

from bs4 import BeautifulSoup
from flask import request

from app import app


def schema_remove(url: str) -> str:
    return re.sub(r"https?://", "", url)


def __url_pack(url: str) -> str:
    return f"{request.host_url}{schema_remove(url)}"


def should_json() -> bool:
    return any(k in ("before", "after") for k in request.args.keys())


def clean_html_for_json(html: str) -> str:
    return re.sub(r"</?html>|</?body>", "", html)


def process_json(data: dict | list | str, url_pack=__url_pack) -> dict | list | str:
    """
    process JSON data by recursively modifying URLs within it.

    args:
        data (dict | list | str): The JSON data to process.
        url_pack (function): A function to pack URLs with the host URL

    returns:
        dict | list | str: The processed JSON data.
    """

    if isinstance(data, str):
        if len(data) < 10:
            return data
        try:
            data = json.loads(data)
        except ValueError:
            return data

    if isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("http"):
                new_data[key] = url_pack(value)
            else:
                new_data[key] = process_json(value, url_pack)
        return json.dumps(new_data)

    elif isinstance(data, list):
        return json.dumps([process_json(item, url_pack) for item in data])

    return data


def process_location_header(location_header: str) -> str:
    """
    Process the 'Location' header in HTTP responses.

    Args:
        location_header (str): The 'Location' header value.

    Returns:
        str: The processed 'Location' header value with the proxy URL if needed.
    """

    proxy_url = request.host_url

    if not re.match(
            r'^' + re.escape(proxy_url) + r'/http://',
            location_header
    ):
        original_url = re.sub(r'^http://', '', location_header)
        location_header = f'{proxy_url}{schema_remove(original_url)}'

    return location_header


def replace_origin_host(html_content: str) -> str:
    """
    Replace URLs in HTML content with proxy URLs.

    Args:
        html_content (str): The HTML content to be processed.

    Returns:
        str: The HTML content with replaced URLs.
    """

    proxy_url = request.host_url

    if should_json():
        html_content = json.loads(html_content)

    soup = BeautifulSoup(html_content, 'lxml')

    replace_url_attributes(soup, proxy_url)
    replace_style_urls(soup, proxy_url)

    output = str(soup)
    output = output.replace(f'/s/{app.config["CHANNEL_NAME"]}', '')

    if should_json():
        output = clean_html_for_json(output)
        return json.dumps(output)

    return output


def replace_url_attributes(soup: BeautifulSoup, proxy_url: str) -> None:
    """
    replace URLs in specified HTML tag attributes with proxy URLs.

    args:
        soup (BeautifulSoup): The BeautifulSoup object representing the HTML content.
        proxy_url (str): The proxy URL to prepend to the original URLs.
    """

    def update_link(tag_element: BeautifulSoup, attribute: str) -> None:
        original_url = tag_element.get(attribute)
        if original_url.split("/")[0] == "static":
            return
        if original_url:
            if original_url.startswith('//'):
                original_url = original_url.replace("//", "")
            tag_element[attribute] = f'{proxy_url}{schema_remove(original_url)}'

    for tag in soup.find_all(('script', 'img', 'video'), src=True):
        update_link(tag, 'src')

    for tag in soup.find_all('link', href=True):
        update_link(tag, 'href')


def replace_style_urls(soup: BeautifulSoup, proxy_url: str) -> None:
    """
    replace URLs in style attributes of HTML tags with proxy URLs.

    args:
        soup (BeautifulSoup): The BeautifulSoup object representing the HTML content.
        proxy_url (str): The proxy URL to prepend to the original URLs.
    """

    def replace_url(match: re.Match) -> str:
        original_url = match.group(1)
        new_url = f'url("{proxy_url}{schema_remove(original_url)}")'
        return new_url

    for tag in soup.find_all(style=True):
        style = tag['style']
        updated_style = re.sub(r'url\([\'"]?([^\'")]+)[\'"]?\)', replace_url, style)
        tag['style'] = updated_style
