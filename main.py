import shutil
import time
import zipfile

import PySimpleGUI as sg
from pathlib import Path
import os
import usersettings
import requests
from appdirs import AppDirs
import tempfile

DEFAULT_PATH = "C:/Program Files/Wizards of the Coast/MTGA/"
APP_NAME = "pl.mtgpopolsku.app"
APP_AUTHOR = "mtgpopolsku"
TRANSLATION_URL = "https://api.github.com/repos/dekoza/mtgpl/releases/latest"
CHUNK_SIZE = 4096

dirs = AppDirs(APP_NAME, APP_AUTHOR)

check_path = Path(DEFAULT_PATH)

s = usersettings.Settings(APP_NAME)
s.add_setting("mtga_path", str, default=DEFAULT_PATH if Path(DEFAULT_PATH).exists() else "")
s.add_setting("backup_path", str, default=dirs.user_data_dir)
s.load_settings()


def get_main_asset(assets):
    for asset in assets:
        if asset["label"] is None:
            return asset
    raise RuntimeError("asset not found")


def check_for_update():
    response = requests.get(TRANSLATION_URL)
    if response.status_code != 200:
        raise ConnectionError("error connecting with server")
    data = response.json()
    return data["tag_name"]


def download_translation(
    file_url: str, file_name: str, destination_path: Path, bar: sg.ProgressBar
) -> Path:
    with open(destination_path / file_name, "wb") as outfile:
        response = requests.get(file_url, stream=True)
        total_length = response.headers.get("content-length")
        # TODO: maybe implement "continue"
        if total_length is None:  # no content length header
            outfile.write(response.content)
        else:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                outfile.write(chunk)
                downloaded += CHUNK_SIZE
                prog_state = int(downloaded * 1000 / int(total_length))
                outfile.flush()
                bar.update(prog_state)
    bar.update(1000)
    return destination_path / file_name


def is_translated(file_path: Path) -> bool:
    with open(file_path) as datfile:
        return "mtgapl" in datfile.read()


def backup_files(file_list: list[str], bar: sg.ProgressBar):
    bar.update(0)
    source_path = Path(s.mtga_path)
    dest_path = Path(dirs.user_data_dir)
    datfiles = [f for f in file_list if f.endswith(".dat")]
    copied = 0
    total_files = len(datfiles)
    for dat_filename in datfiles:
        src_dat_file_path = source_path / dat_filename
        if (not src_dat_file_path.exists()) or is_translated(src_dat_file_path):
            continue
        rel_dir_path = Path(dat_filename).parent
        os.makedirs(dest_path / rel_dir_path, exist_ok=True)
        mtga_filename = dat_filename.removesuffix(".dat")
        src_mtga_file_path = source_path / mtga_filename
        shutil.copy2(src_dat_file_path, dest_path / dat_filename, follow_symlinks=True)
        shutil.copy2(
            src_mtga_file_path, dest_path / mtga_filename, follow_symlinks=True
        )
        copied += 1
        bar.update(int(copied * 1000 / int(total_files)))
    bar.update(1000)


def revert_translation(bar: sg.ProgressBar):
    source_path = Path(dirs.user_data_dir) / "MTGA_Data"
    dest_path = Path(s.mtga_path) / "MTGA_Data"
    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)


def unpack_archive(archive_path, bar: sg.ProgressBar) -> tuple[Path, list[str]]:
    unpacked = 0
    bar.update(0)
    dest_path = archive_path.parent
    with zipfile.ZipFile(archive_path) as archive:
        # shamelessly ripped to support progress bar
        members = archive.namelist()
        total_files = len(members)
        path = os.fspath(dest_path)
        for zipinfo in members:
            archive._extract_member(zipinfo, path, None)
            unpacked += 1
            prog_state = int(unpacked * 1000 / int(total_files))
            bar.update(prog_state)

    bar.update(1000)
    return dest_path, members


def copy_new_files(file_list: list[str], source_path: Path, bar: sg.ProgressBar):
    dest_path = Path(s.mtga_path)
    prog_state = copied = 0
    total_files = len(file_list)
    for filename in file_list:
        bar.update(prog_state)
        shutil.copy2(source_path / filename, dest_path / filename)
        copied += 1
        prog_state = int(copied * 1000 / int(total_files))
    bar.update(1000)


def backups_exist() -> bool:
    dest_path = Path(dirs.user_data_dir)
    return (dest_path / "MTGA_Data/Downloads").exists()


def text_label(text):
    return sg.Text(text + ":", justification="r", size=(20, 1))


def collapsible(layout, key, default_state=False):
    return sg.pin(sg.Column(layout, key=key, visible=default_state))


def create_main_window(settings):
    progress = [
        [sg.Text("", size=(42, 1), font="Any 10", key="-PROG TEXT-")],
        [sg.ProgressBar(1000, orientation="h", size=(42, 20), key="-PROGRESS-")],
        [sg.ProgressBar(1000, orientation="h", size=(42, 20), key="-PROG TOTAL-")],
    ]

    layout = [
        [sg.Text("Spolszczenie MTG Arena", font="Any 15", justification="center")],
        [sg.Text("https://mtgpopolsku.pl", font="Any 10", justification="center")],
        [
            text_label("Zainstalowana wersja"),
            sg.Text(key="-MTGAPL VERSION-", size=(20, 1)),
        ],
        [
            text_label("Najnowsza wesrja"),
            sg.Text(key="-MTGAPL NEWEST-", size=(20, 1)),
            sg.Button("Odśwież"),
        ],
        [collapsible(progress, key="-PROG SECTION-")],
        [
            sg.Button("Instaluj/Aktualizuj"),
            sg.Button("Przywróć oryginalne", disabled=not backups_exist()),
            sg.Button("Ustawienia"),
            sg.Button("Wyjdź"),
        ],
    ]
    window = sg.Window("Spolszczenie MTGA", layout, finalize=True)
    return window


def create_settings_window(settings):
    layout = [
        [sg.Text("Ustawienia", font="Any 15")],
        [
            text_label("Folder MTGA"),
            sg.Input(key="-MTGA PATH-"),
            sg.FolderBrowse(target="-MTGA PATH-"),
        ],
        [sg.Button("Zapisz"), sg.Button("Anuluj")],
    ]

    window = sg.Window("Settings", layout, keep_on_top=True, finalize=True)

    window["-MTGA PATH-"].update(value=settings["mtga_path"])

    return window


def prepare_settings():
    return {
        "mtga_path": s.mtga_path,
    }


def save_settings(values):
    s.mtga_path = values["-MTGA PATH-"]
    s.save_settings()
    return prepare_settings()


def get_data_loc_dat(file_list):
    for f in file_list:
        if f.startswith("data_loc") and f.endswith("dat"):
            return f


def get_installed_version():
    if not (s.mtga_path and (mtga_path := Path(s.mtga_path)).exists()):
        return ""
    path = mtga_path / "MTGA_Data/Downloads/Data"
    if not path.exists():
        return ""
    filename = get_data_loc_dat(os.listdir(path))
    with open(path / filename) as datfile:
        for line in datfile:
            if line.startswith("mtgapl"):
                return line.strip().removeprefix("mtgapl:")


def get_newest_version():
    response = requests.get(TRANSLATION_URL)
    if response.status_code != 200:
        raise ConnectionError("error connecting with server")
    data = response.json()
    return data["tag_name"]


def get_versions():
    return {
        "installed_version": get_installed_version(),
        "newest_version": get_newest_version(),
    }


def main():
    settings = prepare_settings()
    window = create_main_window(settings)
    version_data = get_versions()
    window["-MTGAPL VERSION-"].update(value=version_data["installed_version"])
    window["-MTGAPL NEWEST-"].update(value=version_data["newest_version"])
    small_progress = window.find_element(key="-PROGRESS-")
    total_progress = window.find_element(key="-PROG TOTAL-")
    while True:
        while not settings["mtga_path"]:
            sg.PopupOK("Wybierz folder MTGA")
            # TODO: validation
            event, values = create_settings_window(settings).read(close=True)
            if event == "Zapisz":
                settings = save_settings(values)
            window["-MTGAPL VERSION-"].update(value=get_installed_version())

        event, values = window.read()

        if event in (None, "Wyjdź"):
            break
        if event == "Ustawienia":
            event, values = create_settings_window(settings).read(close=True)
            if event == "Zapisz":
                settings = save_settings(values)
        if event == "Odśwież":
            window["-MTGAPL NEWEST-"].update(value=get_newest_version())

        if event == "Przywróć oryginalne":
            window["-PROG SECTION-"].update(visible=True)
            window["-PROG TEXT-"].update("Przywracam oryginalne pliki...")
            small_progress.update(0)
            total_progress.update(0)
            revert_translation(bar=small_progress)
            total_progress.update(1000)
            window["-PROG TEXT-"].update("Gotowe!")
            time.sleep(1)
            window["-PROG SECTION-"].update(visible=False)

        if event == "Instaluj/Aktualizuj":
            response = requests.get(TRANSLATION_URL)
            if response.status_code != 200:
                raise ConnectionError("error connecting with server")
            data = response.json()

            main_asset = get_main_asset(assets=data["assets"])
            file_url = main_asset["browser_download_url"]
            file_name = main_asset["name"]

            with tempfile.TemporaryDirectory() as tmpdir:
                window["-PROG SECTION-"].update(visible=True)
                small_progress.update(0)
                total_progress.update(0)
                window["-PROG TEXT-"].update("Pobieram tłumaczenie...")
                downloaded_file_path = download_translation(
                    file_url, file_name, Path(tmpdir), bar=small_progress
                )
                total_progress.update(300)
                window["-PROG TEXT-"].update("Rozpakowuję...")
                unpacked_path, file_list = unpack_archive(
                    downloaded_file_path, bar=small_progress
                )
                total_progress.update(500)
                window["-PROG TEXT-"].update("Zabezpieczam oryginalne pliki...")
                backup_files(file_list, bar=small_progress)
                total_progress.update(800)
                window["-PROG TEXT-"].update("Wgrywam tłumaczenie...")
                copy_new_files(file_list, source_path=unpacked_path, bar=small_progress)
                window["-PROG TEXT-"].update("Gotowe!")
                total_progress.update(1000)
                time.sleep(1)
                window["-PROG SECTION-"].update(visible=False)
    window.close()


main()
