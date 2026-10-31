"""Echo bot of the voice probe (docs/portal/VOICE_PROBE.md).

Sits in the probe room. For every audio track named "probe-beep" it publishes a track named
"echo:<identity of the sender>" carrying the same sound back. The probe page sends a beep and waits
for it on its own echo track: both ends are the same page and the same clock, so the round trip
needs no clock sync between machines. The bot runs next to LiveKit, so almost the whole round trip
is the player's network twice plus the server and the codec.
"""
import asyncio
import os
import signal
from importlib.metadata import version

from livekit import api, rtc

URL = os.environ.get("LIVEKIT_URL", "ws://livekit:7880")
KEY = os.environ["LIVEKIT_API_KEY"]
SECRET = os.environ["LIVEKIT_API_SECRET"]
ROOM = os.environ.get("PROBE_ROOM", "probe")
IDENTITY = "echo-bot"
RATE = 48000


def token() -> str:
    grants = api.VideoGrants(room_join=True, room=ROOM, can_publish=True, can_subscribe=True)
    return (api.AccessToken(KEY, SECRET).with_identity(IDENTITY).with_name("echo")
            .with_grants(grants).to_jwt())


class Echo:
    def __init__(self, room: rtc.Room):
        self.room = room
        self.tasks: dict[str, asyncio.Task] = {}   # track sid -> echo task

    def start(self, track: rtc.Track, pub: rtc.RemoteTrackPublication, who: rtc.RemoteParticipant):
        if track.kind != rtc.TrackKind.KIND_AUDIO or pub.name != "probe-beep":
            return
        print(f"echo on for {who.identity}", flush=True)
        self.tasks[pub.sid] = asyncio.ensure_future(self.run(track, who.identity))

    def stop(self, pub_sid: str):
        task = self.tasks.pop(pub_sid, None)
        if task:
            task.cancel()

    async def run(self, track: rtc.Track, identity: str):
        source = rtc.AudioSource(RATE, 1)
        local = rtc.LocalAudioTrack.create_audio_track(f"echo:{identity}", source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        pub = await self.room.local_participant.publish_track(local, opts)
        stream = rtc.AudioStream(track, sample_rate=RATE, num_channels=1)
        try:
            async for ev in stream:
                await source.capture_frame(ev.frame)
        except asyncio.CancelledError:
            pass
        finally:
            await stream.aclose()
            try:
                await self.room.local_participant.unpublish_track(pub.sid)
            except Exception as e:   # the room may be gone already
                print(f"unpublish: {e}", flush=True)
            print(f"echo off for {identity}", flush=True)


async def main():
    print(f"livekit {version('livekit')}, livekit-api {version('livekit-api')}, room {ROOM}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, stop.set)
        except NotImplementedError:   # Windows (a local check outside Docker): Ctrl+C ends it anyway
            pass
    while not stop.is_set():
        room = rtc.Room()
        echo = Echo(room)
        gone = asyncio.Event()
        room.on("track_subscribed", echo.start)
        room.on("track_unpublished", lambda pub, who: echo.stop(pub.sid))
        room.on("disconnected", lambda *a: gone.set())
        # the SDK restores the session by itself, but after its restart the old Room no longer gets
        # new tracks (checked on a LiveKit restart): drop it and join again with a fresh one
        room.on("reconnecting", lambda *a: gone.set())
        try:
            await room.connect(URL, token())
            print("connected", flush=True)
            waits = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(gone.wait())]
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            for w in waits:
                w.cancel()
        except Exception as e:
            # livekit may start after us, or restart after the station's IP changed
            print(f"connect failed: {e}; retry in 5 s", flush=True)
        for sid in list(echo.tasks):
            echo.stop(sid)
        try:
            # mid-reconnect the SDK may never finish disconnect (checked on a LiveKit restart)
            await asyncio.wait_for(room.disconnect(), 5)
        except Exception:
            pass
        print("left the room", flush=True)
        if not stop.is_set():
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
