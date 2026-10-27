from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import TourCategory
from mysite.database.schema import (TourCategoryInputSchema, TourCategoryOutSchema,
                                    TourCategoryUpdateSchema)
from mysite.translations.content import Language, localized, update_translations

category_router = APIRouter(prefix='/tour-categories', tags=['Tour Categories'])


@category_router.post(
    '/', response_model=TourCategoryOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_category(category: TourCategoryInputSchema, db: Session = Depends(get_db)):
    category_db = TourCategory()
    category_db.name = category.name
    category_db.image = category.image

    db.add(category_db)
    update_translations(category_db)
    db.commit()
    db.refresh(category_db)

    return category_db


@category_router.get('/', response_model=list[TourCategoryOutSchema])
def list_category(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    return [
        localized(record, lang)
        for record in db.query(TourCategory).offset(pagination.offset).limit(pagination.limit).all()
    ]


@category_router.get('/{category_id}/', response_model=TourCategoryOutSchema)
def detail_category(category_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(status_code=404, detail='Категория табылган жок')

    return localized(category_db, lang)


@category_router.put(
    '/{category_id}/',
    response_model=TourCategoryOutSchema,
    dependencies=[Depends(get_current_admin)],
)
def update_category(
    category_id: int, category: TourCategoryUpdateSchema, db: Session = Depends(get_db)
):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(status_code=404, detail='Категория табылган жок')

    for key, value in category.model_dump(exclude_unset=True).items():
        setattr(category_db, key, value)

    update_translations(category_db)
    db.commit()
    db.refresh(category_db)

    return category_db


@category_router.delete('/{category_id}/', dependencies=[Depends(get_current_admin)])
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(status_code=404, detail='Категория табылган жок')

    if category_db.tours:
        raise HTTPException(status_code=400, detail='Бул категорияга турлар байланышкан')

    db.delete(category_db)
    db.commit()

    return {'message': 'Категория өчүрүлдү'}


@category_router.post('/setup-directions/', dependencies=[Depends(get_current_admin)])
def setup_directions(db: Session = Depends(get_db)):
    directions = [
        'Высокие горы',
        'Бирюзовые озёра',
        'Кочевая культура',
        'Шёлковый путь',
        'Бескрайние долины',
    ]

    for name in directions:
        category_db = db.query(TourCategory).filter(TourCategory.name == name).first()

        if category_db is None:
            category_db = TourCategory()
            category_db.name = name
            db.add(category_db)

    db.commit()

    categories = db.query(TourCategory).filter(TourCategory.name.in_(directions)).all()

    return {
        'message': '5 багыт даяр',
        'categories': [{'id': category.id, 'name': category.name} for category in categories],
    }
