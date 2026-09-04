from __future__ import annotations

from typing import List

from sqlalchemy.orm import joinedload

from models import ChatMessage, ChatRoom, ChatRoomMember, ChatRoomType, User


GENERAL_ROOM_TITLE = "Командный чат"


def _user_label(user: User | None) -> str:
    if user is None:
        return "Сотрудник"
    return user.full_name or user.login or f"Сотрудник #{user.id}"


def ensure_general_room(session, created_by_user_id: int | None = None) -> ChatRoom:
    room = (
        session.query(ChatRoom)
        .filter(ChatRoom.room_type == ChatRoomType.general, ChatRoom.title == GENERAL_ROOM_TITLE)
        .first()
    )
    if room is None:
        room = ChatRoom(
            room_type=ChatRoomType.general,
            title=GENERAL_ROOM_TITLE,
            description="Внутренний чат команды для быстрых сообщений и координации.",
            created_by_user_id=created_by_user_id,
        )
        session.add(room)
        session.flush()

    member_user_ids = {
        member.user_id for member in session.query(ChatRoomMember).filter(ChatRoomMember.room_id == room.id).all()
    }
    users = session.query(User).filter(User.is_active == True).order_by(User.full_name.asc(), User.login.asc()).all()
    for user in users:
        if user.id not in member_user_ids:
            session.add(ChatRoomMember(room_id=room.id, user_id=user.id))

    session.commit()
    session.refresh(room)
    return room


def list_chat_users(session, current_user_id: int) -> List[User]:
    return (
        session.query(User)
        .filter(User.id != current_user_id, User.is_active == True)
        .order_by(User.full_name.asc(), User.login.asc())
        .all()
    )


def get_or_create_direct_room(session, current_user_id: int, target_user_id: int) -> ChatRoom:
    if current_user_id == target_user_id:
        raise ValueError("Нельзя создать личный чат с самим собой.")

    rooms = (
        session.query(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .filter(ChatRoom.room_type == ChatRoomType.direct, ChatRoomMember.user_id == current_user_id)
        .options(joinedload(ChatRoom.members).joinedload(ChatRoomMember.user))
        .all()
    )

    for room in rooms:
        member_ids = {int(member.user_id) for member in room.members}
        if member_ids == {int(current_user_id), int(target_user_id)}:
            return room

    current_user = session.get(User, current_user_id)
    target_user = session.get(User, target_user_id)
    if target_user is None or not target_user.is_active:
        raise ValueError("Сотрудник для личного чата не найден или деактивирован.")

    room = ChatRoom(
        room_type=ChatRoomType.direct,
        title="Личный чат",
        description=f"Диалог: {_user_label(current_user)} ↔ {_user_label(target_user)}",
        created_by_user_id=current_user_id,
    )
    session.add(room)
    session.flush()
    session.add(ChatRoomMember(room_id=room.id, user_id=current_user_id))
    session.add(ChatRoomMember(room_id=room.id, user_id=target_user_id))
    session.add(
        ChatMessage(
            room_id=room.id,
            user_id=current_user_id,
            body=f"Личный чат создан с сотрудником {_user_label(target_user)}.",
            is_system=True,
        )
    )
    session.commit()
    session.refresh(room)
    return room


def room_display_name(room: ChatRoom, current_user_id: int | None = None) -> str:
    if room.room_type == ChatRoomType.direct and current_user_id is not None:
        for member in room.members:
            if int(member.user_id) != int(current_user_id):
                return _user_label(member.user)
        return "Личный чат"
    return room.title or "Чат"


def room_tooltip(room: ChatRoom, current_user_id: int | None = None) -> str:
    if room.room_type == ChatRoomType.direct:
        return room.description or room_display_name(room, current_user_id)
    return room.description or room.title or "Чат"


def list_rooms_for_user(session, user_id: int) -> List[ChatRoom]:
    ensure_general_room(session, created_by_user_id=user_id)
    return (
        session.query(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .filter(ChatRoomMember.user_id == user_id, ChatRoom.is_archived == False)
        .options(joinedload(ChatRoom.members).joinedload(ChatRoomMember.user))
        .order_by(ChatRoom.created_at.asc(), ChatRoom.id.asc())
        .all()
    )


def list_messages(session, room_id: int, limit: int = 200) -> List[ChatMessage]:
    messages = (
        session.query(ChatMessage)
        .filter(ChatMessage.room_id == room_id)
        .options(joinedload(ChatMessage.user))
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))


def ensure_room_membership(session, room_id: int, user_id: int):
    member = (
        session.query(ChatRoomMember)
        .filter(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
        .first()
    )
    if member is None:
        member = ChatRoomMember(room_id=room_id, user_id=user_id)
        session.add(member)
        session.commit()
    return member


def send_message(session, room_id: int, user_id: int, body: str) -> ChatMessage:
    text = (body or "").strip()
    if not text:
        raise ValueError("Сообщение не может быть пустым.")

    ensure_room_membership(session, room_id, user_id)
    message = ChatMessage(room_id=room_id, user_id=user_id, body=text)
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def mark_room_read(session, room_id: int, user_id: int, message_id: int | None):
    member = ensure_room_membership(session, room_id, user_id)
    member.last_read_message_id = message_id
    session.commit()
