import asyncio
import logging
import uuid
from typing import Callable, Dict, Any, List, Optional, Set

logger = logging.getLogger("shared.ami")

class AMIException(Exception):
    pass

class AMIClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5038, username: str = "superfone", secret: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.secret = secret
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connected = False
        self._read_task: Optional[asyncio.Task] = None
        self._pending_actions: Dict[str, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable[[Dict[str, str]], Any]]] = {}

    def register_event_handler(self, event_name: str, callback: Callable[[Dict[str, str]], Any]):
        """Register a callback for a specific Asterisk AMI Event."""
        event_name = event_name.lower()
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(callback)

    async def connect(self) -> None:
        """Connect to AMI and authenticate."""
        logger.info("Connecting to Asterisk AMI at %s:%d...", self.host, self.port)
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        
        # Read the AMI banner (e.g. "Asterisk Call Manager/9.0.0\r\n")
        banner = await self.reader.readline()
        logger.info("Connected to AMI. Banner: %s", banner.decode().strip())

        # Start reading events in the background (required to receive the response to Login action)
        self.is_connected = True
        self._read_task = asyncio.create_task(self._read_loop())

        # Authenticate
        try:
            login_response = await self.send_action("Login", {
                "Username": self.username,
                "Secret": self.secret
            })
            if login_response.get("Response", "").lower() != "success":
                raise AMIException(f"AMI login failed: {login_response.get('Message', 'Unknown error')}")
        except Exception as e:
            self.is_connected = False
            self._read_task.cancel()
            self.writer.close()
            await self.writer.wait_closed()
            raise e
        
        logger.info("AMI Authenticated successfully as %s", self.username)


    async def disconnect(self) -> None:
        """Disconnect and clean up resources."""
        self.is_connected = False
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        logger.info("Disconnected from AMI.")

    async def send_action(self, action: str, params: Dict[str, str]) -> Dict[str, str]:
        """Send an AMI action and await its response."""
        action_id = str(uuid.uuid4())
        payload = f"Action: {action}\r\nActionID: {action_id}\r\n"
        for k, v in params.items():
            payload += f"{k}: {v}\r\n"
        payload += "\r\n"

        future = asyncio.get_running_loop().create_future()
        self._pending_actions[action_id] = future

        try:
            self.writer.write(payload.encode("utf-8"))
            await self.writer.drain()
            
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=5.0)
            return response
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for response to action %s (ActionID: %s)", action, action_id)
            raise AMIException(f"AMI Action {action} timed out")
        finally:
            self._pending_actions.pop(action_id, None)

    async def _read_loop(self) -> None:
        """Loop to read raw message blocks from AMI stream."""
        try:
            current_block = {}
            while self.is_connected:
                line_bytes = await self.reader.readline()
                if not line_bytes:
                    logger.warning("AMI connection lost (EOF).")
                    break
                
                line = line_bytes.decode("utf-8").strip()
                if line == "":
                    # Empty line indicates end of a message block
                    if current_block:
                        self._process_message_block(current_block)
                        current_block = {}
                else:
                    parts = line.split(": ", 1)
                    if len(parts) == 2:
                        current_block[parts[0]] = parts[1]
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in AMI read loop: %s", e, exc_info=True)
        finally:
            self.is_connected = False

    def _process_message_block(self, block: Dict[str, str]) -> None:
        """Determine if block is a Response or an Event and dispatch it."""
        action_id = block.get("ActionID")
        
        # If this is a response to a pending action, resolve the future
        if "Response" in block and action_id in self._pending_actions:
            self._pending_actions[action_id].set_result(block)
            return

        # Otherwise, check if it is an event
        event_name = block.get("Event")
        if event_name:
            handlers = self._event_handlers.get(event_name.lower(), [])
            for handler in handlers:
                try:
                    # Execute callback asynchronously if needed or directly
                    if asyncio.iscoroutinefunction(handler):
                        asyncio.create_task(handler(block))
                    else:
                        handler(block)
                except Exception as e:
                    logger.error("Error in AMI event handler %s: %s", handler, e, exc_info=True)


class AMIRegistry:
    client: Optional[AMIClient] = None
    uuid_to_channel: Dict[str, str] = {}
    active_channels: Set[str] = set()
    channel_to_uuid: Dict[str, str] = {}

    @classmethod
    async def get_channel_by_uuid(cls, uuid_str: str) -> str:
        """Gets the Asterisk channel name by its UUID. Uses active Getvar recovery if needed."""
        uuid_str = uuid_str.lower()
        chan = cls.uuid_to_channel.get(uuid_str)
        if chan:
            return chan

        logger.warning("UUID %s not found in mapping cache. Triggering active recovery lookup...", uuid_str)
        if not cls.client or not cls.client.is_connected:
            raise AMIException("AMI client not connected, cannot run recovery lookup")

        # Iterate over active channels
        for active_chan in list(cls.active_channels):
            try:
                res = await cls.client.send_action("Getvar", {
                    "Channel": active_chan,
                    "Variable": "AUDIO_UUID_VAR"
                })
                if res.get("Response", "").lower() == "success":
                    val = res.get("Value", "").strip().lower()
                    if val == uuid_str:
                        logger.info("AMI Recovery: Successfully matched active channel %s with UUID %s", active_chan, uuid_str)
                        cls.uuid_to_channel[uuid_str] = active_chan
                        cls.channel_to_uuid[active_chan] = uuid_str
                        return active_chan
            except Exception as e:
                logger.error("Error querying variable AUDIO_UUID_VAR on channel %s: %s", active_chan, e)

        raise AMIException(f"Failed to resolve Asterisk channel name for UUID {uuid_str}")

