import os
import requests
from github import Github
from github import Auth
import configparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup as bs
from pathlib import Path
from tqdm import tqdm


def get_default_config(filename):
    cf = configparser.ConfigParser()
    cf.read(filename)
    config = {
        "server_api": cf.get("server", "server_api"),
        "force_manual_login": cf.get("user", "force_manual_login"),
        "github_name": cf.get("user", "github_name"),
        "github_password": cf.get("user", "github_password"),
        "release_tag_mark": cf.get("release", "release_tag_mark"),
        "release_file_list": cf.get("release", "release_file_list"),
        "output_path": cf.get("output", "output_path"),
    }
    return config


def recreate_directory(dir_path):
    try:
        # Create a Path object
        p = Path(dir_path)

        # Check if the directory exists
        if p.exists():
            # Recursively delete the directory
            for sub in p.iterdir():
                if sub.is_dir():
                    sub.rmdir()
                else:
                    sub.unlink()

            # Re-create the directory
            p.mkdir(parents=True, exist_ok=True)
        else:
            # If the directory does not exist, create it directly
            p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"An error occurred: {e}")


def is_valid_url(url_string):
    try:
        result = urlparse(url_string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def is_valid_tag_release_link(tag_release_link, tag_mark):
    if is_valid_url(tag_release_link) and tag_mark in tag_release_link:
        return bool(get_substring_after(tag_release_link, tag_mark))
    return False


def get_base_url(url):
    parsed_url = urlparse(url)
    return parsed_url.scheme + '://' + parsed_url.netloc


def get_substring_after(text, delimiter):
    parts = text.split(delimiter, 1)
    return parts[1] if len(parts) == 2 else ''


def get_substring_between(text, start, end):
    parts = text.split(start)[1:]
    extracted_substrings = [end.join(part.split(end)[:-1]) for part in parts]
    return ' '.join(extracted_substrings)


def download_asset(asset, session, session_headers, download_output_path):
    try:
        response = session.get(asset.browser_download_url, headers=session_headers, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        # Set a threshold for small files
        small_file_threshold = 1024  # 1 KB

        if total_size < small_file_threshold:
            with open(download_output_path + "\\" + asset.name, 'wb') as file:
                file.write(response.content)
            print(f'{asset.name} downloaded successfully')
        else:
            block_size = 1024  # 1 KB
            with open(download_output_path + "\\" + asset.name, 'wb') as file:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=asset.name, ncols=100) as pbar:
                    for data in response.iter_content(block_size):
                        file.write(data)
                        pbar.update(len(data))
            print(f'{asset.name} downloaded successfully')
    except requests.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except Exception as e:
        print(f"Failed to download release assets. Error: {e}")


def fetch_release_assets(release, to_download_list, session, session_headers, download_output_path):
    assets = release.get_assets()
    if to_download_list:
        to_be_download_count = len(to_download_list)
    else:
        to_be_download_count = assets.totalCount
    download_index = 1
    for asset in assets:
        if not to_download_list or asset.name in to_download_list:
            print(download_index, "/", to_be_download_count, ":")
            download_asset(asset, session, session_headers, download_output_path)
            download_index = download_index+1


def main():
    current_cfg = get_default_config(r'default.config')

    release_tag_link = input("Please enter the release link for a specific software:")
    while not is_valid_tag_release_link(release_tag_link, current_cfg["release_tag_mark"]):
        print("Invalid release link. Please check and try again or close the program.")
        release_tag_link = input("Please enter the release link again:")

    if current_cfg["force_manual_login"] == 'TRUE':
        login_name = input("Please enter your GitHub username:")
        login_password = input("Please enter your GitHub password:")
    else:
        login_name = current_cfg["github_name"]
        login_password = current_cfg["github_password"]

    try:
        auth = Auth.Login(login_name, login_password)
        github_instance = Github(base_url=get_base_url(release_tag_link) + "/" + current_cfg["server_api"], auth=auth)
        user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/77.0.3865.120 Safari/537.36')
        session_headers = {'user-agent': user_agent}
        login_url = get_base_url(release_tag_link) + "/" + "session"
        session = requests.Session()
        response = session.get(login_url, headers=session_headers)
        authenticity_token_onetime = bs(response.text, 'lxml').find('input', attrs={'name': 'authenticity_token'})[
            'value']
        print(authenticity_token_onetime)
        session.post(
            login_url,
            headers=session_headers,
            data=dict(
                commit='Sign in',
                utf8='%E2%9C%93',
                login=login_name,
                password=login_password,
                authenticity_token=authenticity_token_onetime
            )
        )
        user = github_instance.get_user()
        print(f"Login successful! Current user: {user.name}")

        repo_name = get_substring_between(release_tag_link, get_base_url(release_tag_link) + '/',
                                          current_cfg["release_tag_mark"])
        repo = github_instance.get_repo(repo_name)
        print(f"Repository located successfully! Current repository: {repo_name}")

        release_tag = get_substring_after(release_tag_link, current_cfg["release_tag_mark"])
        release = repo.get_release(release_tag)
        print(f"Release tag found! Current tag: {release_tag}")
        if current_cfg["output_path"] == '':
            download_output_path = os.getcwd()
        else:
            download_output_path = current_cfg["output_path"]
        download_output_path = download_output_path + "\\" + release_tag
        recreate_directory(download_output_path)
        print(download_output_path)
        # print(release.body)

        to_download_list = current_cfg["release_file_list"].split() if current_cfg["release_file_list"] else []
        fetch_release_assets(release, to_download_list, session, session_headers, download_output_path)

        input("Press Enter key to exit:")

    except requests.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
