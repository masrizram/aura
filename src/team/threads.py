"""Discussion thread system for AURA audit findings.

Team members discuss findings, share evidence attachments, and track resolution.
Threads persist alongside finding state for full audit trail traceability.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class Comment:
    id: str
    finding_id: str
    author_id: str
    content: str
    timestamp: str
    attachments: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    resolved: bool = False
    parent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "author_id": self.author_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "attachments": self.attachments,
            "mentions": self.mentions,
            "resolved": self.resolved,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Comment":
        return cls(
            id=data["id"],
            finding_id=data["finding_id"],
            author_id=data["author_id"],
            content=data["content"],
            timestamp=data["timestamp"],
            attachments=data.get("attachments", []),
            mentions=data.get("mentions", []),
            resolved=data.get("resolved", False),
            parent_id=data.get("parent_id"),
        )


class ThreadManager:
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._threads_file = self.state_dir / "finding-threads.json"
        self._threads: Dict[str, List[Comment]] = {}
        self._load()

    def _load(self) -> None:
        if not self._threads_file.exists():
            return
        try:
            data = json.loads(self._threads_file.read_text(encoding="utf-8"))
            for fid, comments_data in data.items():
                self._threads[fid] = [Comment.from_dict(c) for c in comments_data]
        except (json.JSONDecodeError, KeyError, IOError):
            self._threads = {}

    def _save(self) -> None:
        data = {
            fid: [c.to_dict() for c in comments]
            for fid, comments in self._threads.items()
        }
        self._threads_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_comment(self, finding_id: str, author_id: str, content: str,
                     attachments: Optional[List[str]] = None,
                     parent_id: Optional[str] = None) -> Comment:
        content = content.strip()
        if not content:
            raise ValueError("Comment content must not be empty")

        mentions = self._extract_mentions(content)

        comment = Comment(
            id=f"cmt-{uuid.uuid4().hex[:12]}",
            finding_id=finding_id,
            author_id=author_id,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            attachments=attachments or [],
            mentions=mentions,
            parent_id=parent_id,
        )

        self._threads.setdefault(finding_id, []).append(comment)
        self._save()
        return comment

    def _extract_mentions(self, content: str) -> List[str]:
        import re
        return re.findall(r"@([a-zA-Z0-9._-]+)", content)

    def get_thread(self, finding_id: str) -> List[Comment]:
        thread = self._threads.get(finding_id, [])
        thread.sort(key=lambda c: c.timestamp)
        return thread

    def get_comment(self, comment_id: str) -> Optional[Comment]:
        for thread in self._threads.values():
            for c in thread:
                if c.id == comment_id:
                    return c
        return None

    def get_mentions(self, member_id: str) -> List[Comment]:
        result: List[Comment] = []
        for thread in self._threads.values():
            for c in thread:
                if member_id in c.mentions:
                    result.append(c)
        result.sort(key=lambda c: c.timestamp, reverse=True)
        return result

    def get_unread_mentions(self, member_id: str, since: str) -> List[Comment]:
        all_mentions = self.get_mentions(member_id)
        return [c for c in all_mentions if c.timestamp > since]

    def resolve_thread(self, finding_id: str) -> bool:
        if finding_id not in self._threads:
            return False
        for comment in self._threads[finding_id]:
            comment.resolved = True
        self._save()
        return True

    def is_resolved(self, finding_id: str) -> bool:
        thread = self._threads.get(finding_id)
        if not thread:
            return True
        return all(c.resolved for c in thread)

    def comment_count(self, finding_id: str) -> int:
        return len(self._threads.get(finding_id, []))

    def active_threads(self) -> Set[str]:
        return {
            fid for fid, thread in self._threads.items()
            if not self.is_resolved(fid)
        }

    def finding_thread_summary(self, finding_id: str) -> Dict[str, Any]:
        thread = self.get_thread(finding_id)
        authors = set(c.author_id for c in thread)
        all_mentions = [m for c in thread for m in c.mentions]
        return {
            "finding_id": finding_id,
            "comment_count": len(thread),
            "authors": sorted(authors),
            "mentions": sorted(set(all_mentions)),
            "first_comment": thread[0].timestamp if thread else None,
            "last_comment": thread[-1].timestamp if thread else None,
            "is_resolved": self.is_resolved(finding_id),
            "attachment_count": sum(len(c.attachments) for c in thread),
        }

    def search_threads(self, query: str) -> List[Comment]:
        query_lower = query.lower()
        results: List[Comment] = []
        for thread in self._threads.values():
            for c in thread:
                if query_lower in c.content.lower():
                    results.append(c)
        results.sort(key=lambda c: c.timestamp, reverse=True)
        return results

    def export_thread(self, finding_id: str) -> str:
        thread = self.get_thread(finding_id)
        if not thread:
            return f"# Thread for {finding_id}\n\n*No comments*\n"

        lines = [f"# Thread for {finding_id}", "", f"**{len(thread)} comment(s)**", ""]
        for c in thread:
            status = " [RESOLVED]" if c.resolved else ""
            lines.append(f"## {c.author_id} — {c.timestamp}{status}")
            lines.append("")
            lines.append(c.content)
            if c.attachments:
                lines.append("")
                lines.append("Attachments: " + ", ".join(c.attachments))
            if c.mentions:
                lines.append(f"Mentions: {', '.join('@' + m for m in c.mentions)}")
            lines.append("")
        return "\n".join(lines)