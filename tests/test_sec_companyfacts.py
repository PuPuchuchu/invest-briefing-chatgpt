def fetch_json(url: str) -> dict:

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        },
        method="GET",
    )

    with urlopen(request, timeout=30) as response:

        status = response.status
        content_encoding = (
            response.headers.get("Content-Encoding", "")
            .lower()
        )

        raw_data = response.read()

        print(f"HTTP status: {status}")
        print(
            f"Content-Encoding: "
            f"{content_encoding or 'none'}"
        )
        print(
            f"Response bytes: "
            f"{len(raw_data)}"
        )

        if status != 200:
            raise RuntimeError(
                f"HTTP status: {status}"
            )

        if content_encoding == "gzip":

            import gzip

            raw_data = gzip.decompress(
                raw_data
            )

        elif content_encoding == "deflate":

            import zlib

            raw_data = zlib.decompress(
                raw_data
            )

        text = raw_data.decode(
            "utf-8"
        )

        return json.loads(text)