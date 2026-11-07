from enum import Enum

from mysite.database.models import RequestStatusChoices


class SelectionStatus(str, Enum):
    draft = 'draft'
    in_progress = 'in_progress'
    completed = 'completed'
    cancelled = 'cancelled'


SELECTION_TO_REQUEST_STATUS = {
    SelectionStatus.in_progress: RequestStatusChoices.in_progress,
    SelectionStatus.completed: RequestStatusChoices.completed,
    SelectionStatus.cancelled: RequestStatusChoices.cancelled,
}
