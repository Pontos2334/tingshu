from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import PromptTemplate, AIGeneration, Setting
from app.models import (
    AIGenerateRequest, AIGenerationOut,
    PromptTemplateCreate, PromptTemplateUpdate, PromptTemplateOut,
)
from app.services.ai_service import generate_content
from app.config import settings

router = APIRouter()


@router.post("/generate", response_model=AIGenerationOut)
async def ai_generate(req: AIGenerateRequest, db: AsyncSession = Depends(get_db)):
    # 获取 API key
    result = await db.execute(select(Setting).where(Setting.key == "deepseek_api_key"))
    row = result.scalar_one_or_none()
    api_key = row.value if row else settings.deepseek_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="未配置 DeepSeek API Key，请在设置中配置")

    # 获取 base_url
    result = await db.execute(select(Setting).where(Setting.key == "deepseek_base_url"))
    row = result.scalar_one_or_none()
    base_url = row.value if row else settings.deepseek_base_url

    # 解析 prompt
    model = req.model
    if req.template_id:
        result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.id == req.template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        system_prompt = template.system_prompt
        user_prompt = template.user_prompt_template.replace("{topic}", req.topic)
        model = model or template.model
        # 注入风格参考
        if template.style_example:
            system_prompt = system_prompt + "\n\n以下是风格参考文章，请模仿其写作风格、语气、句式和表达习惯：\n\n" + template.style_example
    else:
        system_prompt = req.system_prompt or "你是一个专业的有声书内容创作者。请输出纯文本，不要使用 Markdown 格式。"
        user_prompt = req.user_prompt or req.topic

    try:
        generated_text = await generate_content(
            api_key, base_url, model, system_prompt, user_prompt, req.max_tokens,
            thinking_enabled=req.thinking_enabled,
            reasoning_effort=req.reasoning_effort,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 生成失败: {str(e)}")

    # 保存到历史
    record = AIGeneration(
        template_id=req.template_id,
        topic=req.topic,
        generated_text=generated_text,
        model=model,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


# 提示词模板 CRUD
@router.get("/templates", response_model=list[PromptTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptTemplate).order_by(PromptTemplate.is_default.desc(), PromptTemplate.id)
    )
    return result.scalars().all()


@router.get("/templates/{template_id}", response_model=PromptTemplateOut)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


@router.post("/templates", response_model=PromptTemplateOut)
async def create_template(req: PromptTemplateCreate, db: AsyncSession = Depends(get_db)):
    import re
    # 自动生成 slug
    slug = re.sub(r'[^a-z0-9]+', '-', req.name.lower()).strip('-')
    # 检查 slug 唯一性
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.slug == slug))
    if result.scalar_one_or_none():
        import uuid
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    template = PromptTemplate(
        slug=slug,
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        user_prompt_template=req.user_prompt_template,
        style_example=req.style_example,
        model=req.model,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.put("/templates/{template_id}", response_model=PromptTemplateOut)
async def update_template(template_id: int, req: PromptTemplateUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    update_data = req.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    if template.is_default:
        raise HTTPException(status_code=400, detail="不能删除默认模板")

    await db.delete(template)
    await db.commit()
    return {"message": "模板已删除"}


# 生成历史
@router.get("/history")
async def list_history(page: int = 1, size: int = 20, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    offset = (page - 1) * size

    result = await db.execute(
        select(AIGeneration)
        .order_by(AIGeneration.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    items = result.scalars().all()

    count_result = await db.execute(select(func.count(AIGeneration.id)))
    total = count_result.scalar() or 0

    return {
        "items": [AIGenerationOut.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.delete("/history/{generation_id}")
async def delete_history(generation_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIGeneration).where(AIGeneration.id == generation_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    await db.delete(record)
    await db.commit()
    return {"message": "记录已删除"}
