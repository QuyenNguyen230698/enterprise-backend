from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# 1. Khởi tạo Engine (Động cơ kết nối)
engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # Keep SQL logs off; only errors should surface.
    future=True, # Báo cho SQLAlchemy biết ta đang dùng chuẩn mới nhất (2.0)
    pool_size=10, # Giới hạn số kết nối đồng thời để không làm chết DB
    max_overflow=20
)

# 2. Khởi tạo Session Factory (Nơi sản xuất ra các phiên làm việc với DB)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 3. Dependency Injection (Hàm này sẽ được cắm vào các Route FastAPI)
# Cách này đảm bảo: Mở kết nối -> Truy vấn -> Luôn luôn đóng kết nối dù có lỗi xảy ra.
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()