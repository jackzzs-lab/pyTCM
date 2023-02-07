from setuptools import setup, find_packages

setup(
    name="protactm",
    version="1.0",
    description="A package for evaluating, developing, and testing PROTAC ternary complex modeling protocols",
    url="https://github.com/jackzzs-lab/protactm",
    author="Zhesheng Zhou",
    author_email="zhouzzs@foxmail.com",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.8",
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'ptm = protactm.cli:cli'
        ]
    },
)
