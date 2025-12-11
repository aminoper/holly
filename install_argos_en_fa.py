import argostranslate.package
import argostranslate.translate

# آپدیت لیست پکیج‌ها از اینترنت
argostranslate.package.update_package_index()
available_packages = argostranslate.package.get_available_packages()

# پیدا کردن پکیج انگلیسی → فارسی
packages_en_fa = [
    p for p in available_packages
    if p.from_code == "en" and p.to_code == "fa"
]

if not packages_en_fa:
    print("هیچ پکیج en → fa پیدا نشد. شاید اینترنت مشکل دارد.")
else:
    pkg = packages_en_fa[0]
    print(f"در حال دانلود و نصب پکیج: {pkg}")
    download_path = pkg.download()
    argostranslate.package.install_from_path(download_path)
    print("✅ پکیج en → fa برای Argos نصب شد.")