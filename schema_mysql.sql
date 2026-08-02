-- MediaCrawler MySQL 建表 SQL
-- 生成时间: 2026-04-01
-- 数据库: media_crawler

CREATE DATABASE IF NOT EXISTS `media_crawler` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `media_crawler`;

-- B站视频表
CREATE TABLE IF NOT EXISTS `bilibili_video` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `video_id` BIGINT NOT NULL COMMENT '视频ID',
  `video_url` TEXT NOT NULL COMMENT '视频URL',
  `user_id` BIGINT COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `liked_count` INT COMMENT '点赞数',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `video_type` TEXT COMMENT '视频类型',
  `title` TEXT COMMENT '视频标题',
  `desc` TEXT COMMENT '视频描述',
  `create_time` BIGINT COMMENT '创建时间戳',
  `disliked_count` TEXT COMMENT '点踩数',
  `video_play_count` TEXT COMMENT '播放数',
  `video_favorite_count` TEXT COMMENT '收藏数',
  `video_share_count` TEXT COMMENT '分享数',
  `video_coin_count` TEXT COMMENT '硬币数',
  `video_danmaku` TEXT COMMENT '弹幕数',
  `video_comment` TEXT COMMENT '评论数',
  `video_cover_url` TEXT COMMENT '视频封面URL',
  `source_keyword` TEXT COMMENT '来源关键词',
  PRIMARY KEY (`id`),
  UNIQUE KEY `video_id` (`video_id`),
  KEY `user_id` (`user_id`),
  KEY `create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站视频表';

-- B站视频评论表
CREATE TABLE IF NOT EXISTS `bilibili_video_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `sex` TEXT COMMENT '性别',
  `sign` TEXT COMMENT '签名',
  `avatar` TEXT COMMENT '头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `comment_id` BIGINT COMMENT '评论ID',
  `video_id` BIGINT COMMENT '视频ID',
  `content` TEXT COMMENT '评论内容',
  `create_time` BIGINT COMMENT '创建时间戳',
  `sub_comment_count` TEXT COMMENT '子评论数',
  `parent_comment_id` VARCHAR(255) COMMENT '父评论ID',
  `like_count` TEXT   COMMENT '点赞数',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `video_id` (`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站视频评论表';

-- B站UP主信息表
CREATE TABLE IF NOT EXISTS `bilibili_up_info` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` BIGINT COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `sex` TEXT COMMENT '性别',
  `sign` TEXT COMMENT '签名',
  `avatar` TEXT COMMENT '头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `total_fans` INT COMMENT '总粉丝数',
  `total_liked` INT COMMENT '总获赞数',
  `user_rank` INT COMMENT '用户等级',
  `is_official` INT COMMENT '是否官方认证',
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站UP主信息表';

-- B站UP主联系方式表
CREATE TABLE IF NOT EXISTS `bilibili_contact_info` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `up_id` BIGINT COMMENT 'UP主ID',
  `fan_id` BIGINT COMMENT '粉丝ID',
  `up_name` TEXT COMMENT 'UP主名称',
  `fan_name` TEXT COMMENT '粉丝名称',
  `up_sign` TEXT COMMENT 'UP主签名',
  `fan_sign` TEXT COMMENT '粉丝签名',
  `up_avatar` TEXT COMMENT 'UP主头像',
  `fan_avatar` TEXT COMMENT '粉丝头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  KEY `up_id` (`up_id`),
  KEY `fan_id` (`fan_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站UP主联系方式表';

-- B站UP主动态表
CREATE TABLE IF NOT EXISTS `bilibili_up_dynamic` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `dynamic_id` BIGINT COMMENT '动态ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `user_name` TEXT COMMENT '用户名称',
  `text` TEXT COMMENT '动态内容',
  `type` TEXT COMMENT '动态类型',
  `pub_ts` BIGINT COMMENT '发布时间戳',
  `total_comments` INT COMMENT '总评论数',
  `total_forwards` INT COMMENT '总转发数',
  `total_liked` INT COMMENT '总点赞数',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  KEY `dynamic_id` (`dynamic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站UP主动态表';

-- 抖音作品表
CREATE TABLE IF NOT EXISTS `douyin_aweme` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `sec_uid` VARCHAR(255) COMMENT '安全用户ID',
  `short_user_id` VARCHAR(255) COMMENT '短用户ID',
  `user_unique_id` VARCHAR(255) COMMENT '用户唯一ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `user_signature` TEXT COMMENT '用户签名',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `aweme_id` BIGINT COMMENT '作品ID',
  `aweme_type` TEXT COMMENT '作品类型',
  `title` TEXT COMMENT '作品标题',
  `desc` TEXT COMMENT '作品描述',
  `create_time` BIGINT COMMENT '创建时间戳',
  `liked_count` TEXT COMMENT '点赞数',
  `comment_count` TEXT COMMENT '评论数',
  `share_count` TEXT COMMENT '分享数',
  `collected_count` TEXT COMMENT '收藏数',
  `aweme_url` TEXT COMMENT '作品URL',
  `cover_url` TEXT COMMENT '封面URL',
  `video_download_url` TEXT COMMENT '视频下载URL',
  `music_download_url` TEXT COMMENT '音乐下载URL',
  `note_download_url` TEXT COMMENT '笔记下载URL',
  `source_keyword` TEXT   COMMENT '来源关键词',
  PRIMARY KEY (`id`),
  KEY `aweme_id` (`aweme_id`),
  KEY `create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抖音作品表';

-- 抖音作品评论表
CREATE TABLE IF NOT EXISTS `douyin_aweme_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `sec_uid` VARCHAR(255) COMMENT '安全用户ID',
  `short_user_id` VARCHAR(255) COMMENT '短用户ID',
  `user_unique_id` VARCHAR(255) COMMENT '用户唯一ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `user_signature` TEXT COMMENT '用户签名',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `comment_id` BIGINT COMMENT '评论ID',
  `aweme_id` BIGINT COMMENT '作品ID',
  `content` TEXT COMMENT '评论内容',
  `create_time` BIGINT COMMENT '创建时间戳',
  `sub_comment_count` TEXT COMMENT '子评论数',
  `parent_comment_id` VARCHAR(255) COMMENT '父评论ID',
  `like_count` TEXT  COMMENT '点赞数',
  `pictures` TEXT   COMMENT '图片',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `aweme_id` (`aweme_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抖音作品评论表';

-- 抖音创作者表
CREATE TABLE IF NOT EXISTS `dy_creator` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `desc` TEXT COMMENT '描述',
  `gender` TEXT COMMENT '性别',
  `follows` TEXT COMMENT '关注数',
  `fans` TEXT COMMENT '粉丝数',
  `interaction` TEXT COMMENT '互动数',
  `videos_count` VARCHAR(255) COMMENT '视频数量',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抖音创作者表';

-- 快手视频表
CREATE TABLE IF NOT EXISTS `kuaishou_video` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(64) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `video_id` VARCHAR(255) COMMENT '视频ID',
  `video_type` TEXT COMMENT '视频类型',
  `title` TEXT COMMENT '视频标题',
  `desc` TEXT COMMENT '视频描述',
  `create_time` BIGINT COMMENT '创建时间戳',
  `liked_count` TEXT COMMENT '点赞数',
  `viewd_count` TEXT COMMENT '观看数',
  `video_url` TEXT COMMENT '视频URL',
  `video_cover_url` TEXT COMMENT '视频封面URL',
  `video_play_url` TEXT COMMENT '视频播放URL',
  `source_keyword` TEXT   COMMENT '来源关键词',
  PRIMARY KEY (`id`),
  KEY `video_id` (`video_id`),
  KEY `create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='快手视频表';

-- 快手视频评论表
CREATE TABLE IF NOT EXISTS `kuaishou_video_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` TEXT COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `comment_id` BIGINT COMMENT '评论ID',
  `video_id` VARCHAR(255) COMMENT '视频ID',
  `content` TEXT COMMENT '评论内容',
  `create_time` BIGINT COMMENT '创建时间戳',
  `sub_comment_count` TEXT COMMENT '子评论数',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `video_id` (`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='快手视频评论表';

-- 微博笔记表
CREATE TABLE IF NOT EXISTS `weibo_note` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `gender` TEXT COMMENT '性别',
  `profile_url` TEXT COMMENT '个人主页URL',
  `ip_location` TEXT   COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `note_id` BIGINT COMMENT '笔记ID',
  `content` TEXT COMMENT '笔记内容',
  `create_time` BIGINT COMMENT '创建时间戳',
  `create_date_time` VARCHAR(255) COMMENT '创建日期时间',
  `liked_count` TEXT COMMENT '点赞数',
  `comments_count` TEXT COMMENT '评论数',
  `shared_count` TEXT COMMENT '分享数',
  `note_url` TEXT COMMENT '笔记URL',
  `source_keyword` TEXT  COMMENT '来源关键词',
  PRIMARY KEY (`id`),
  KEY `note_id` (`note_id`),
  KEY `create_time` (`create_time`),
  KEY `create_date_time` (`create_date_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='微博笔记表';

-- 微博笔记评论表
CREATE TABLE IF NOT EXISTS `weibo_note_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `gender` TEXT COMMENT '性别',
  `profile_url` TEXT COMMENT '个人主页URL',
  `ip_location` TEXT  COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `comment_id` BIGINT COMMENT '评论ID',
  `note_id` BIGINT COMMENT '笔记ID',
  `content` TEXT COMMENT '评论内容',
  `create_time` BIGINT COMMENT '创建时间戳',
  `create_date_time` VARCHAR(255) COMMENT '创建日期时间',
  `comment_like_count` TEXT COMMENT '评论点赞数',
  `sub_comment_count` TEXT COMMENT '子评论数',
  `parent_comment_id` VARCHAR(255) COMMENT '父评论ID',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `note_id` (`note_id`),
  KEY `create_date_time` (`create_date_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='微博笔记评论表';

-- 微博创作者表
CREATE TABLE IF NOT EXISTS `weibo_creator` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `desc` TEXT COMMENT '描述',
  `gender` TEXT COMMENT '性别',
  `follows` TEXT COMMENT '关注数',
  `fans` TEXT COMMENT '粉丝数',
  `tag_list` TEXT COMMENT '标签列表',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='微博创作者表';

-- 小红书创作者表
CREATE TABLE IF NOT EXISTS `xhs_creator` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `desc` TEXT COMMENT '描述',
  `gender` TEXT COMMENT '性别',
  `follows` TEXT COMMENT '关注数',
  `fans` TEXT COMMENT '粉丝数',
  `interaction` TEXT COMMENT '互动数',
  `tag_list` TEXT COMMENT '标签列表',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='小红书创作者表';

-- 小红书笔记表
CREATE TABLE IF NOT EXISTS `xhs_note` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `note_id` VARCHAR(255) COMMENT '笔记ID',
  `type` TEXT COMMENT '笔记类型',
  `title` TEXT COMMENT '笔记标题',
  `desc` TEXT COMMENT '笔记描述',
  `video_url` TEXT COMMENT '视频URL',
  `time` BIGINT COMMENT '时间戳',
  `last_update_time` BIGINT COMMENT '最后更新时间戳',
  `liked_count` TEXT COMMENT '点赞数',
  `collected_count` TEXT COMMENT '收藏数',
  `comment_count` TEXT COMMENT '评论数',
  `share_count` TEXT COMMENT '分享数',
  `image_list` TEXT COMMENT '图片列表',
  `tag_list` TEXT COMMENT '标签列表',
  `note_url` TEXT COMMENT '笔记URL',
  `source_keyword` TEXT   COMMENT '来源关键词',
  `xsec_token` TEXT COMMENT 'Xsec Token',
  PRIMARY KEY (`id`),
  KEY `note_id` (`note_id`),
  KEY `time` (`time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='小红书笔记表';

-- 小红书笔记评论表
CREATE TABLE IF NOT EXISTS `xhs_note_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `comment_id` VARCHAR(255) COMMENT '评论ID',
  `create_time` BIGINT COMMENT '创建时间戳',
  `note_id` VARCHAR(255) COMMENT '笔记ID',
  `content` TEXT COMMENT '评论内容',
  `sub_comment_count` INT COMMENT '子评论数',
  `pictures` TEXT COMMENT '图片',
  `parent_comment_id` VARCHAR(255) COMMENT '父评论ID',
  `like_count` TEXT COMMENT '点赞数',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='小红书笔记评论表';

-- 百度贴吧帖子表
CREATE TABLE IF NOT EXISTS `tieba_note` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `note_id` VARCHAR(64) NOT NULL COMMENT '帖子ID',
  `title` VARCHAR(500) DEFAULT NULL COMMENT '帖子标题',
  `desc` TEXT COMMENT '帖子描述',
  `note_url` VARCHAR(500) DEFAULT NULL COMMENT '帖子URL',
  `publish_time` VARCHAR(50) DEFAULT NULL COMMENT '发布时间',
  `user_link` VARCHAR(500) DEFAULT NULL COMMENT '用户链接',
  `user_nickname` VARCHAR(200) DEFAULT NULL COMMENT '用户昵称',
  `user_avatar` VARCHAR(500) DEFAULT NULL COMMENT '用户头像',
  `tieba_id` VARCHAR(100) DEFAULT '' COMMENT '贴吧ID',
  `tieba_name` VARCHAR(200) DEFAULT NULL COMMENT '贴吧名称',
  `tieba_link` VARCHAR(500) DEFAULT NULL COMMENT '贴吧链接',
  `total_reply_num` INT DEFAULT 0 COMMENT '总回复数',
  `total_reply_page` INT DEFAULT 0 COMMENT '总回复页数',
  `ip_location` VARCHAR(100) DEFAULT NULL COMMENT 'IP地址位置',
  `add_ts` BIGINT DEFAULT NULL COMMENT '添加时间戳',
  `last_modify_ts` BIGINT DEFAULT NULL COMMENT '最后修改时间戳',
  `source_keyword` VARCHAR(200) DEFAULT NULL COMMENT '来源关键词',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_note_id` (`note_id`),
  KEY `idx_publish_time` (`publish_time`),
  KEY `idx_tieba_id` (`tieba_id`),
  KEY `idx_add_ts` (`add_ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='百度贴吧帖子表';

-- 百度贴吧评论表
CREATE TABLE IF NOT EXISTS `tieba_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `comment_id` VARCHAR(255) COMMENT '评论ID',
  `parent_comment_id` VARCHAR(255) DEFAULT '' COMMENT '父评论ID',
  `content` TEXT COMMENT '评论内容',
  `user_link` TEXT   COMMENT '用户链接',
  `user_nickname` TEXT   COMMENT '用户昵称',
  `user_avatar` TEXT   COMMENT '用户头像',
  `tieba_id` VARCHAR(255) DEFAULT '' COMMENT '贴吧ID',
  `tieba_name` TEXT COMMENT '贴吧名称',
  `tieba_link` TEXT COMMENT '贴吧链接',
  `publish_time` VARCHAR(255) COMMENT '发布时间',
  `ip_location` TEXT   COMMENT 'IP地址位置',
  `sub_comment_count` INT DEFAULT 0 COMMENT '子评论数',
  `note_id` VARCHAR(255) COMMENT '帖子ID',
  `note_url` TEXT COMMENT '帖子URL',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `publish_time` (`publish_time`),
  KEY `note_id` (`note_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='百度贴吧评论表';

-- 百度贴吧创作者表
CREATE TABLE IF NOT EXISTS `tieba_creator` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(64) COMMENT '用户ID',
  `user_name` TEXT COMMENT '用户名',
  `nickname` TEXT COMMENT '用户昵称',
  `avatar` TEXT COMMENT '用户头像',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  `gender` TEXT COMMENT '性别',
  `follows` TEXT COMMENT '关注数',
  `fans` TEXT COMMENT '粉丝数',
  `registration_duration` TEXT COMMENT '注册时长',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='百度贴吧创作者表';

-- 知乎内容表
CREATE TABLE IF NOT EXISTS `zhihu_content` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `content_id` VARCHAR(64) COMMENT '内容ID',
  `content_type` TEXT COMMENT '内容类型',
  `content_text` TEXT COMMENT '内容文本',
  `content_url` TEXT COMMENT '内容URL',
  `question_id` VARCHAR(255) COMMENT '问题ID',
  `title` TEXT COMMENT '标题',
  `desc` TEXT COMMENT '描述',
  `created_time` VARCHAR(32) COMMENT '创建时间',
  `updated_time` TEXT COMMENT '更新时间',
  `voteup_count` INT DEFAULT 0 COMMENT '赞同数',
  `comment_count` INT DEFAULT 0 COMMENT '评论数',
  `source_keyword` TEXT COMMENT '来源关键词',
  `user_id` VARCHAR(255) COMMENT '用户ID',
  `user_link` TEXT COMMENT '用户链接',
  `user_nickname` TEXT COMMENT '用户昵称',
  `user_avatar` TEXT COMMENT '用户头像',
  `user_url_token` TEXT COMMENT '用户URL Token',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  KEY `content_id` (`content_id`),
  KEY `created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知乎内容表';

-- 知乎评论表
CREATE TABLE IF NOT EXISTS `zhihu_comment` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `comment_id` VARCHAR(64) COMMENT '评论ID',
  `parent_comment_id` VARCHAR(64) COMMENT '父评论ID',
  `content` TEXT COMMENT '评论内容',
  `publish_time` VARCHAR(32) COMMENT '发布时间',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `sub_comment_count` INT DEFAULT 0 COMMENT '子评论数',
  `like_count` INT DEFAULT 0 COMMENT '点赞数',
  `dislike_count` INT DEFAULT 0 COMMENT '点踩数',
  `content_id` VARCHAR(64) COMMENT '内容ID',
  `content_type` TEXT COMMENT '内容类型',
  `user_id` VARCHAR(64) COMMENT '用户ID',
  `user_link` TEXT COMMENT '用户链接',
  `user_nickname` TEXT COMMENT '用户昵称',
  `user_avatar` TEXT COMMENT '用户头像',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  KEY `comment_id` (`comment_id`),
  KEY `publish_time` (`publish_time`),
  KEY `content_id` (`content_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知乎评论表';

-- 知乎创作者表
CREATE TABLE IF NOT EXISTS `zhihu_creator` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` VARCHAR(64) COMMENT '用户ID',
  `user_link` TEXT COMMENT '用户链接',
  `user_nickname` TEXT COMMENT '用户昵称',
  `user_avatar` TEXT COMMENT '用户头像',
  `url_token` TEXT COMMENT 'URL Token',
  `gender` TEXT COMMENT '性别',
  `ip_location` TEXT COMMENT 'IP地址位置',
  `follows` INT DEFAULT 0 COMMENT '关注数',
  `fans` INT DEFAULT 0 COMMENT '粉丝数',
  `anwser_count` INT DEFAULT 0 COMMENT '回答数',
  `video_count` INT DEFAULT 0 COMMENT '视频数',
  `question_count` INT DEFAULT 0 COMMENT '问题数',
  `article_count` INT DEFAULT 0 COMMENT '文章数',
  `column_count` INT DEFAULT 0 COMMENT '专栏数',
  `get_voteup_count` INT DEFAULT 0 COMMENT '获赞数',
  `add_ts` BIGINT COMMENT '添加时间戳',
  `last_modify_ts` BIGINT COMMENT '最后修改时间戳',
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知乎创作者表';
