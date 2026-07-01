def normalize_storage_path(file_url: str):
    if not file_url:
        return None

    file_path = file_url

    if "/notes/" in file_path:
        file_path = file_path.split("/notes/")[-1]

    if file_path.startswith("notes/"):
        file_path = file_path.replace("notes/", "", 1)

    return file_path